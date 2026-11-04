from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta
from typing import Any, Optional, Protocol

import numpy as np
import pandas as pd

from .clock import shanghai_now
from .config import Candidate, Theme
from .macro_news import map_macro_news, match_sector_for_theme
from .providers.common import format_money, pct_fmt, serialize_kline, to_number


class MarketProvider(Protocol):
    def us_quote(self, ticker: str) -> dict[str, Any]: ...

    def us_history(self, ticker: str, start: date, end: date) -> pd.DataFrame: ...

    def a_snapshot(self, code: str) -> dict[str, Any]: ...

    def a_history(self, code: str, start: date, end: date) -> pd.DataFrame: ...

    def stock_news(self, code: str, name: str = "", limit: int = 5) -> list[dict[str, str]]: ...


POSITIVE_NEWS_WORDS = [
    "订单",
    "增长",
    "预增",
    "扭亏",
    "回购",
    "合作",
    "中标",
    "突破",
    "量产",
    "扩产",
    "涨价",
    "政策",
    "获批",
    "创新高",
    "机构调研",
]

NEGATIVE_NEWS_WORDS = [
    "减持",
    "亏损",
    "处罚",
    "问询",
    "立案",
    "下滑",
    "诉讼",
    "终止",
    "风险",
    "解禁",
    "质押",
]

# Positive weights in the legacy profile sum to 0.96. Risk stays a separate
# penalty so the old numeric scale is unchanged. China-local v1 keeps that
# 0.96 sum and moves 0.22 onto the local catalyst from US signal, history, and momentum.
LEGACY_WEIGHTS = {
    "signal": 0.34,
    "history": 0.32,
    "momentum": 0.12,
    "liquidity": 0.08,
    "news": 0.10,
    "china_catalyst": 0.0,
}
CHINA_LOCAL_WEIGHTS = {
    "signal": 0.24,
    "history": 0.22,
    "momentum": 0.10,
    "liquidity": 0.08,
    "news": 0.10,
    "china_catalyst": 0.22,
}
SCORING_PROFILES = {
    "legacy": {
        "label": "旧口径",
        "weights": LEGACY_WEIGHTS,
        "note": "美股主题信号 34%、历史次日 32%、动量 12%、流动性 8%、个股新闻 10%，正向权重合计 96%，风险另扣。回测继续使用这一口径，因为历史政策、涨停情绪和板块资金无法逐日复原。",
    },
    "china_local_v1": {
        "label": "中国本地催化",
        "weights": CHINA_LOCAL_WEIGHTS,
        "note": "美股主题信号 24%、历史次日 22%、中国本地催化 22%、动量 10%、个股新闻 10%、流动性 8%，正向权重合计 96%，风险另扣。中国本地催化综合政策/宏观新闻映射、涨停与跌停家数、主题板块涨跌，以及个股量比、换手和成交额。缺失的分项保持中性，不把没有读到的数据当成利好或利空。输出是研究候选和风险提示，不是买入指令。",
    },
}


def rank_report(
    themes: list[Theme],
    provider: MarketProvider,
    *,
    report_date: date,
    top_n: int = 5,
    lookback_days: int = 420,
    skip_news: bool = False,
    max_themes: Optional[int] = None,
    skip_macro: bool = False,
    legacy_weights: bool = False,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    start = report_date - timedelta(days=lookback_days)
    moment = shanghai_now(now)
    china_inputs, scoring = prepare_china_scoring(
        themes,
        provider,
        report_date=report_date,
        skip_macro=skip_macro,
        legacy_weights=legacy_weights,
        now=moment,
    )
    theme_blocks: list[dict[str, Any]] = []

    ranked_theme_inputs: list[tuple[Theme, Optional[dict[str, Any]]]]
    if max_themes:
        signal_pairs = [(theme, current_theme_signal(theme, provider)) for theme in themes]
        signal_pairs.sort(key=lambda item: item[1]["score"], reverse=True)
        ranked_theme_inputs = [(theme, signal) for theme, signal in signal_pairs[:max_themes]]
    else:
        ranked_theme_inputs = [(theme, None) for theme in themes]

    for theme, signal in ranked_theme_inputs:
        block = rank_theme(
            theme,
            provider,
            start=start,
            end=report_date,
            top_n=top_n,
            skip_news=skip_news,
            precomputed_signal=signal,
            china_inputs=china_inputs,
            weight_profile=scoring["profile"],
        )
        theme_blocks.append(block)

    theme_blocks.sort(key=lambda item: item["signal"]["score"], reverse=True)
    leaders = _sector_leaders(china_inputs.get("boards") or [])

    return {
        "date": str(report_date),
        "generated_at": moment.isoformat(),
        "themes": theme_blocks,
        "macro": china_inputs.get("macro") or {},
        "china_market": {
            "overview": _public_market_overview(china_inputs.get("market") or {}),
            "sector_leaders": leaders,
            "warnings": china_inputs.get("warnings") or [],
        },
        "scoring": scoring,
    }


def rank_theme(
    theme: Theme,
    provider: MarketProvider,
    *,
    start: date,
    end: date,
    top_n: int,
    skip_news: bool,
    precomputed_signal: Optional[dict[str, Any]] = None,
    china_inputs: Optional[dict[str, Any]] = None,
    weight_profile: str = "legacy",
) -> dict[str, Any]:
    signal = precomputed_signal or current_theme_signal(theme, provider)
    theme_series = historical_theme_series(theme, provider, start, end)
    ranked: list[dict[str, Any]] = []
    theme_policy = ((china_inputs or {}).get("macro") or {}).get("themes", {}).get(theme.id, {})
    sector = match_sector_for_theme(theme, (china_inputs or {}).get("boards") or []) if weight_profile == "china_local_v1" else None
    market = (china_inputs or {}).get("market") or {}

    for candidate in theme.candidates:
        snapshot = _safe_call(lambda: provider.a_snapshot(candidate.code), default={})
        hist = _safe_call(lambda: provider.a_history(candidate.code, start, end), default=pd.DataFrame())
        snapshot = enrich_snapshot_from_history(snapshot, hist)
        stats = historical_stats(hist, theme_series)
        news = [] if skip_news else _safe_call(lambda: provider.stock_news(candidate.code, candidate.name, 5), default=[])
        news_score, news_hits, news_risks = score_news(news)
        china = china_catalyst_score(
            policy_score=theme_policy.get("score"),
            policy_available=bool(theme_policy.get("available")),
            market=market if weight_profile == "china_local_v1" else {},
            sector=sector,
            snapshot=snapshot if weight_profile == "china_local_v1" else {},
        )
        total, factors = score_candidate(
            signal,
            stats,
            snapshot,
            news_score,
            candidate,
            weight_profile=weight_profile,
            china_catalyst=china["score"] if weight_profile == "china_local_v1" else None,
            policy_score=theme_policy.get("score") if weight_profile == "china_local_v1" and theme_policy.get("available") else None,
        )
        analyst = analyst_profile(
            total,
            signal,
            stats,
            snapshot,
            news_score,
            news_hits,
            news_risks,
            candidate,
            china_catalyst_score=china["score"] if weight_profile == "china_local_v1" else None,
            weight_profile=weight_profile,
        )
        ranked.append(
            {
                "candidate": asdict(candidate),
                "snapshot": snapshot,
                "stats": stats,
                "news": news,
                "kline": serialize_kline(hist, limit=120),
                "news_hits": news_hits,
                "news_risks": news_risks,
                "score": round(total, 2),
                "factors": factors,
                "analyst": analyst,
                "formatted": format_candidate(candidate, snapshot, stats, news, total),
                "china_catalyst": china if weight_profile == "china_local_v1" else None,
            }
        )

    ranked.sort(key=lambda item: item["score"], reverse=True)
    return {
        "theme": asdict(theme),
        "signal": signal,
        "top": ranked[:top_n],
        "all": ranked,
        "china_context": {
            "policy_score": theme_policy.get("score"),
            "policy_available": bool(theme_policy.get("available")),
            "headlines": theme_policy.get("headlines") or [],
            "sector": sector,
        },
    }


def current_theme_signal(theme: Theme, provider: MarketProvider) -> dict[str, Any]:
    quotes: list[dict[str, Any]] = []
    weighted_sum = 0.0
    weight_sum = 0.0
    positive = 0
    for ticker in theme.us_tickers:
        quote = _safe_call(lambda t=ticker: provider.us_quote(t.ticker), default={"ticker": ticker.ticker, "pct": None})
        pct = to_number(quote.get("pct"))
        quote["weight"] = ticker.weight
        quote["configured_name"] = ticker.name
        quotes.append(quote)
        if pct is None:
            continue
        weighted_sum += pct * ticker.weight
        weight_sum += ticker.weight
        positive += 1 if pct > 0 else 0

    avg_pct = weighted_sum / weight_sum if weight_sum else 0.0
    breadth = positive / weight_sum if weight_sum else 0.0
    score = clamp(50 + avg_pct * 9 + breadth * 10, 0, 100)
    return {
        "avg_pct": round(avg_pct, 3),
        "score": round(score, 2),
        "breadth": round(breadth, 3),
        "quotes": quotes,
        "summary": _signal_summary(quotes),
    }


def historical_theme_series(theme: Theme, provider: MarketProvider, start: date, end: date) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for ticker in theme.us_tickers:
        hist = _safe_call(lambda t=ticker: provider.us_history(t.ticker, start, end), default=pd.DataFrame())
        if hist is None or hist.empty:
            continue
        frame = hist[["date", "pct"]].copy()
        frame["weighted_pct"] = pd.to_numeric(frame["pct"], errors="coerce") * ticker.weight
        frame["weight"] = ticker.weight
        frames.append(frame[["date", "weighted_pct", "weight"]])
    if not frames:
        return pd.DataFrame(columns=["date", "theme_pct"])
    raw = pd.concat(frames, ignore_index=True)
    grouped = raw.groupby("date", as_index=False).agg(weighted_pct=("weighted_pct", "sum"), weight=("weight", "sum"))
    grouped["theme_pct"] = grouped["weighted_pct"] / grouped["weight"].replace(0, np.nan)
    return grouped[["date", "theme_pct"]].dropna().sort_values("date")


def historical_stats(a_hist: pd.DataFrame, theme_series: pd.DataFrame, signal_threshold: float = 1.0) -> dict[str, Any]:
    if a_hist is None or a_hist.empty or theme_series is None or theme_series.empty:
        return _empty_stats()
    a = a_hist[["date", "pct"]].dropna().copy().sort_values("date")
    us = theme_series[["date", "theme_pct"]].dropna().copy().sort_values("date")
    if a.empty or us.empty:
        return _empty_stats()

    # A-share date C can react to the latest completed US session before C.
    a["signal_cutoff"] = a["date"] - pd.Timedelta(days=1)
    merged = pd.merge_asof(a, us, left_on="signal_cutoff", right_on="date", direction="backward", suffixes=("_a", "_us"))
    merged = merged.dropna(subset=["pct", "theme_pct"])
    if merged.empty:
        return _empty_stats()

    signal_days = merged[merged["theme_pct"] >= signal_threshold]
    positive_days = merged[merged["theme_pct"] > 0]
    corr = merged["pct"].corr(merged["theme_pct"]) if len(merged) >= 8 else np.nan
    var = merged["theme_pct"].var()
    beta = merged["pct"].cov(merged["theme_pct"]) / var if var and not np.isnan(var) else np.nan
    hit_rate = (signal_days["pct"] > 0).mean() if not signal_days.empty else np.nan
    avg_after_signal = signal_days["pct"].mean() if not signal_days.empty else np.nan
    avg_after_positive = positive_days["pct"].mean() if not positive_days.empty else np.nan
    return {
        "samples": int(len(merged)),
        "signal_samples": int(len(signal_days)),
        "hit_rate": _float_or_none(hit_rate),
        "avg_after_signal": _float_or_none(avg_after_signal),
        "avg_after_positive": _float_or_none(avg_after_positive),
        "corr": _float_or_none(corr),
        "beta": _float_or_none(beta),
    }


def score_candidate(
    signal: dict[str, Any],
    stats: dict[str, Any],
    snapshot: dict[str, Any],
    news_score: float,
    candidate: Candidate,
    *,
    weight_profile: str = "legacy",
    china_catalyst: Optional[float] = None,
    policy_score: Optional[float] = None,
) -> tuple[float, dict[str, float]]:
    weights = SCORING_PROFILES.get(weight_profile, SCORING_PROFILES["legacy"])["weights"]
    signal_component = signal["score"] * weights["signal"]

    hit_rate = stats.get("hit_rate")
    avg_after_signal = stats.get("avg_after_signal")
    corr = stats.get("corr")
    beta = stats.get("beta")
    history_raw = 50.0
    if hit_rate is not None:
        history_raw += (hit_rate - 0.5) * 70
    if avg_after_signal is not None:
        history_raw += avg_after_signal * 4
    if corr is not None:
        history_raw += corr * 15
    if beta is not None:
        history_raw += clamp(beta, -1.5, 1.8) * 5
    history_component = clamp(history_raw, 0, 100) * weights["history"]

    day_pct = to_number(snapshot.get("pct")) or 0.0
    turnover = to_number(snapshot.get("turnover_rate")) or 0.0
    momentum_raw = 50 + clamp(day_pct, -6, 6) * 3 + clamp(turnover, 0, 12)
    momentum_component = clamp(momentum_raw, 0, 100) * weights["momentum"]

    market_cap = to_number(snapshot.get("market_cap"))
    liquidity_raw = 55
    if market_cap:
        if market_cap >= 100_000_000_000:
            liquidity_raw += 12
        elif market_cap < 8_000_000_000:
            liquidity_raw -= 14
    liquidity_component = clamp(liquidity_raw, 0, 100) * weights["liquidity"]

    news_component = clamp(50 + news_score * 10, 0, 100) * weights["news"]
    china_raw = 50.0 if china_catalyst is None else float(china_catalyst)
    china_component = clamp(china_raw, 0, 100) * weights["china_catalyst"]
    risk_penalty = risk_penalty_points(snapshot, candidate, news_score)
    if policy_score is not None and policy_score <= -3 and weights["china_catalyst"] > 0:
        risk_penalty += min(6.0, abs(float(policy_score)))

    total = signal_component + history_component + momentum_component + liquidity_component + news_component + china_component - risk_penalty
    factors = {
        "signal": round(signal_component, 2),
        "history": round(history_component, 2),
        "momentum": round(momentum_component, 2),
        "liquidity": round(liquidity_component, 2),
        "news": round(news_component, 2),
        "china_catalyst": round(china_component, 2),
        "risk_penalty": round(risk_penalty, 2),
    }
    return clamp(total, 0, 100), factors


def analyst_profile(
    total: float,
    signal: dict[str, Any],
    stats: dict[str, Any],
    snapshot: dict[str, Any],
    news_score: float,
    news_hits: list[str],
    news_risks: list[str],
    candidate: Candidate,
    *,
    china_catalyst_score: Optional[float] = None,
    weight_profile: str = "legacy",
) -> dict[str, Any]:
    catalyst = clamp(signal.get("score", 50), 0, 100)
    history_edge = history_edge_score(stats)
    quality_proxy = quality_proxy_score(snapshot)
    momentum = momentum_score(snapshot)
    news = clamp(50 + news_score * 10, 0, 100)
    risk_points = risk_penalty_points(snapshot, candidate, news_score)
    risk_gate = risk_gate_for(snapshot, risk_points, news_risks)
    conviction = conviction_score(
        catalyst,
        history_edge,
        quality_proxy,
        momentum,
        news,
        stats,
        risk_gate,
        china=china_catalyst_score,
        weight_profile=weight_profile,
    )
    rating = analyst_rating(total, conviction, risk_gate)
    entry_plan = entry_plan_text(snapshot, rating)
    scenario = scenario_for(snapshot, stats, signal)
    dimensions = {
        "catalyst": round(catalyst, 1),
        "history_edge": round(history_edge, 1),
        "quality_proxy": round(quality_proxy, 1),
        "momentum": round(momentum, 1),
        "news": round(news, 1),
        "risk": round(max(0, 100 - risk_points * 5), 1),
    }
    method = "Top-down catalyst + historical edge + liquidity/quality proxy + momentum + event/risk gate"
    if weight_profile == "china_local_v1":
        dimensions["china_catalyst"] = round(clamp(50 if china_catalyst_score is None else china_catalyst_score, 0, 100), 1)
        method = "US catalyst + China local catalyst (policy, limit-up sentiment, sector move, turnover) + historical edge + liquidity proxy + event/risk gate. Research candidates only, not a buy order."
    return {
        "rating": rating,
        "conviction": round(conviction, 1),
        "risk_gate": risk_gate,
        "entry_plan": entry_plan,
        "scenario": scenario,
        "dimensions": dimensions,
        "positive_flags": news_hits[:4],
        "risk_flags": news_risks[:4],
        "method": method,
    }


def history_edge_score(stats: dict[str, Any]) -> float:
    if not stats or not stats.get("samples"):
        return 45.0
    score = 50.0
    hit_rate = stats.get("hit_rate")
    avg_after_signal = stats.get("avg_after_signal")
    corr = stats.get("corr")
    beta = stats.get("beta")
    samples = stats.get("signal_samples") or 0
    if hit_rate is not None:
        score += (hit_rate - 0.5) * 90
    if avg_after_signal is not None:
        score += avg_after_signal * 5
    if corr is not None:
        score += corr * 18
    if beta is not None:
        score += clamp(beta, -1.5, 1.8) * 4
    if samples < 20:
        score -= 8
    elif samples >= 60:
        score += 4
    return clamp(score, 0, 100)


def quality_proxy_score(snapshot: dict[str, Any]) -> float:
    market_cap = to_number(snapshot.get("market_cap"))
    turnover = to_number(snapshot.get("turnover_rate")) or 0
    pe = to_number(snapshot.get("pe"))
    score = 50.0
    if market_cap:
        if market_cap >= 200_000_000_000:
            score += 18
        elif market_cap >= 80_000_000_000:
            score += 12
        elif market_cap < 8_000_000_000:
            score -= 15
    if 1 <= turnover <= 8:
        score += 8
    elif turnover > 15:
        score -= 6
    if pe is not None:
        if 0 < pe < 45:
            score += 6
        elif pe > 120:
            score -= 8
    return clamp(score, 0, 100)


def momentum_score(snapshot: dict[str, Any]) -> float:
    day_pct = to_number(snapshot.get("pct")) or 0.0
    turnover = to_number(snapshot.get("turnover_rate")) or 0.0
    score = 50 + clamp(day_pct, -6, 6) * 4
    if 1.2 <= turnover <= 8:
        score += 8
    elif turnover > 15:
        score -= 8
    if day_pct >= 8.5:
        score -= 12
    return clamp(score, 0, 100)


def risk_gate_for(snapshot: dict[str, Any], risk_points: float, news_risks: list[str]) -> str:
    day_pct = to_number(snapshot.get("pct"))
    name = str(snapshot.get("name", ""))
    if "ST" in name.upper() or "退" in name:
        return "Block"
    if risk_points >= 12 or len(news_risks) >= 2:
        return "Block"
    if day_pct is not None and day_pct >= 8.5:
        return "Watch"
    if risk_points >= 5 or news_risks:
        return "Watch"
    return "Pass"


def conviction_score(
    catalyst: float,
    history_edge: float,
    quality_proxy: float,
    momentum: float,
    news: float,
    stats: dict[str, Any],
    risk_gate: str,
    *,
    china: Optional[float] = None,
    weight_profile: str = "legacy",
) -> float:
    if weight_profile == "china_local_v1":
        china_score = 50.0 if china is None else china
        score = catalyst * 0.20 + history_edge * 0.22 + quality_proxy * 0.14 + momentum * 0.12 + news * 0.12 + china_score * 0.20
    else:
        score = catalyst * 0.26 + history_edge * 0.28 + quality_proxy * 0.16 + momentum * 0.15 + news * 0.15
    signal_samples = stats.get("signal_samples") or 0
    if signal_samples >= 60:
        score += 5
    elif signal_samples < 20:
        score -= 6
    if risk_gate == "Watch":
        score -= 8
    elif risk_gate == "Block":
        score -= 25
    return clamp(score, 0, 100)


def analyst_rating(total: float, conviction: float, risk_gate: str) -> str:
    if risk_gate == "Block":
        return "Avoid"
    if total >= 76 and conviction >= 70 and risk_gate == "Pass":
        return "Buy"
    if total >= 68 and conviction >= 62:
        return "Outperform"
    if total >= 58:
        return "Neutral"
    return "Underperform"


def entry_plan_text(snapshot: dict[str, Any], rating: str) -> str:
    price = to_number(snapshot.get("price"))
    day_pct = to_number(snapshot.get("pct"))
    if rating in {"Avoid", "Underperform"}:
        return "不进入交易池，等待风险解除或评分修复。"
    if day_pct is not None and day_pct >= 8.5:
        return "高开/急涨过大，等待回落确认，不追价。"
    if price:
        if rating == "Buy":
            return f"回踩至 {price * 0.97:.2f}-{price * 1.01:.2f} 分批，跌破 {price * 0.91:.2f} 复核。"
        return f"观察 {price * 0.95:.2f}-{price * 1.00:.2f} 区间，放量确认再参与。"
    return "等待开盘价、成交额和风险闸门确认。"


def scenario_for(snapshot: dict[str, Any], stats: dict[str, Any], signal: dict[str, Any]) -> dict[str, str]:
    avg = stats.get("avg_after_signal")
    signal_pct = signal.get("avg_pct")
    day_pct = to_number(snapshot.get("pct"))
    base = avg if avg is not None else (signal_pct or 0) * 0.35
    bull = base + max(0.8, abs(signal_pct or 0) * 0.4)
    bear = -max(1.0, abs(day_pct or 0) * 0.35, abs(base) * 0.45)
    return {
        "bull": f"若板块扩散且成交放大，1-3 日弹性约 {bull:+.2f}%。",
        "base": f"基准情景参考历史映射，期望约 {base:+.2f}%。",
        "bear": f"若高开回落或负面新闻发酵，回撤压力约 {bear:+.2f}%。",
    }


def score_news(news: list[dict[str, str]]) -> tuple[float, list[str], list[str]]:
    positive_hits: list[str] = []
    risk_hits: list[str] = []
    for item in news:
        title = item.get("title", "")
        for word in POSITIVE_NEWS_WORDS:
            if word in title:
                positive_hits.append(word)
        for word in NEGATIVE_NEWS_WORDS:
            if word in title:
                risk_hits.append(word)
    score = len(set(positive_hits)) * 0.8 - len(set(risk_hits)) * 1.1
    return score, sorted(set(positive_hits)), sorted(set(risk_hits))


def risk_penalty_points(snapshot: dict[str, Any], candidate: Candidate, news_score: float) -> float:
    penalty = 0.0
    name = snapshot.get("name") or candidate.name
    if "ST" in str(name).upper() or "退" in str(name):
        penalty += 30
    day_pct = to_number(snapshot.get("pct"))
    if day_pct is not None and day_pct >= 8.5:
        penalty += 10
    if news_score < -1:
        penalty += min(12, abs(news_score) * 2)
    return penalty


def enrich_snapshot_from_history(snapshot: dict[str, Any], hist: pd.DataFrame) -> dict[str, Any]:
    enriched = dict(snapshot or {})
    latest = None
    if hist is not None and not hist.empty:
        latest_frame = hist.dropna(subset=["close"]).sort_values("date")
        if not latest_frame.empty:
            latest = latest_frame.iloc[-1]

    if latest is not None:
        latest_close = to_number(latest.get("close"))
        latest_pct = to_number(latest.get("pct"))
        if to_number(enriched.get("price")) is None and latest_close is not None:
            enriched["price"] = latest_close
        if latest_pct is not None:
            enriched["last_kline_pct"] = latest_pct
            enriched["last_kline_date"] = pd.Timestamp(latest.get("date")).strftime("%Y-%m-%d")

    if to_number(enriched.get("pct")) is not None and "pct_source" not in enriched:
        enriched["pct_source"] = "snapshot"
    return enriched


def format_candidate(
    candidate: Candidate,
    snapshot: dict[str, Any],
    stats: dict[str, Any],
    news: list[dict[str, str]],
    score: float,
) -> dict[str, str]:
    news_titles = []
    for item in news[:3]:
        title = item.get("title", "")
        when = item.get("time", "")
        source = item.get("source", "")
        prefix = " / ".join(part for part in [when, source] if part)
        news_titles.append(f"{prefix}: {title}" if prefix else title)
    hit_rate = stats.get("hit_rate")
    avg = stats.get("avg_after_signal")
    pct_source = snapshot.get("pct_source")
    pct_asof = " ".join(str(part) for part in [snapshot.get("pct_date"), snapshot.get("snapshot_time")] if part)
    return {
        "code": candidate.code,
        "name": snapshot.get("name") or candidate.name,
        "industry": snapshot.get("industry") or candidate.industry or "未知",
        "market_cap": format_money(snapshot.get("market_cap")),
        "day_pct": pct_fmt(snapshot.get("pct")),
        "day_pct_source": pct_source_label(pct_source),
        "day_pct_asof": pct_asof,
        "price": price_fmt(snapshot.get("price")),
        "score": f"{score:.1f}",
        "hit_rate": f"{hit_rate * 100:.1f}%" if hit_rate is not None else "样本不足",
        "avg_after_signal": pct_fmt(avg),
        "rationale": candidate.rationale,
        "news": "；".join(news_titles) if news_titles else "暂无可用新闻",
    }


def pct_source_label(value: Any) -> str:
    if value == "eastmoney_snapshot":
        return "东财实时"
    if value == "sina_snapshot":
        return "新浪实时"
    if value == "snapshot":
        return "实时快照"
    if value == "not_open":
        return "未开盘/无成交"
    if value == "latest_kline":
        return "最近K线"
    return ""


def price_fmt(value: Any) -> str:
    num = to_number(value)
    if num is None:
        return "未知"
    return f"{num:.2f}"


def _signal_summary(quotes: list[dict[str, Any]], limit: int = 5) -> str:
    available = [q for q in quotes if to_number(q.get("pct")) is not None]
    available.sort(key=lambda item: to_number(item.get("pct")) or 0, reverse=True)
    return "，".join(f"{q.get('ticker')} {pct_fmt(q.get('pct'))}" for q in available[:limit]) or "暂无可用美股信号"


def _empty_stats() -> dict[str, Any]:
    return {
        "samples": 0,
        "signal_samples": 0,
        "hit_rate": None,
        "avg_after_signal": None,
        "avg_after_positive": None,
        "corr": None,
        "beta": None,
    }


def prepare_china_scoring(
    themes: list[Theme],
    provider: Any,
    *,
    report_date: date,
    skip_macro: bool,
    legacy_weights: bool,
    now: datetime,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load local catalysts. Live tape is only applied when the report date is today."""
    warnings: list[str] = []
    use_live = report_date == now.date() and not legacy_weights
    news: list[dict[str, Any]] = []
    market: dict[str, Any] = {"available": False}
    boards: list[dict[str, Any]] = []
    if not use_live:
        if legacy_weights:
            warnings.append("已按 --legacy-weights 使用旧评分权重。")
        elif skip_macro:
            warnings.append("已跳过宏观/政策新闻。")
        else:
            warnings.append("历史日期不回填当日实时政策与盘口，评分回退到旧权重。")
    else:
        if skip_macro:
            warnings.append("已跳过宏观/政策新闻抓取。")
        else:
            news = _provider_call(provider, "macro_news", [], 40) or []
            if any(str(item.get("stale") or "") in {"1", "true"} for item in news):
                warnings.append("宏观/政策新闻使用了过期缓存。")
        market = _provider_call(provider, "market_overview", {"available": False}) or {"available": False}
        if not market.get("available"):
            warnings.append("涨停家数或两市成交额暂不可用。")
        boards = _provider_call(provider, "sector_boards", [], 24) or []
        if not boards:
            warnings.append("板块涨幅暂不可用。")
    macro = map_macro_news(news, themes, asof=now)
    alive = bool(macro.get("available")) or bool(market.get("available")) or bool(boards)
    profile = "china_local_v1" if use_live and alive else "legacy"
    scoring = {
        "profile": profile,
        "requested_profile": "legacy" if legacy_weights else "china_local_v1",
        "label": SCORING_PROFILES[profile]["label"],
        "weights": SCORING_PROFILES[profile]["weights"],
        "positive_weight_sum": round(sum(SCORING_PROFILES[profile]["weights"].values()), 2),
        "note": SCORING_PROFILES[profile]["note"],
        "fallback": "",
        "warnings": warnings,
    }
    if scoring["requested_profile"] == "china_local_v1" and profile == "legacy":
        scoring["fallback"] = "中国本地催化数据不可用或与报告日期不匹配，本次回退到旧权重，避免用缺失数据改写排序。"
    return {"macro": macro, "market": market, "boards": boards, "warnings": warnings, "alive": alive}, scoring


def china_catalyst_score(
    *,
    policy_score: Optional[float],
    policy_available: bool,
    market: Optional[dict[str, Any]],
    sector: Optional[dict[str, Any]],
    snapshot: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """0-100 local catalyst. Missing parts stay at the neutral 50 base and do not pretend to be news."""
    score = 50.0
    available = False
    parts: dict[str, Any] = {}
    if policy_available:
        available = True
        delta = clamp(float(policy_score or 0), -8, 8) * 3.0
        score += delta
        parts["policy"] = round(delta, 2)
        parts["policy_raw"] = round(float(policy_score or 0), 3)
    overview = market or {}
    if overview.get("available") and overview.get("limit_up_count") is not None:
        available = True
        limit_up = float(overview["limit_up_count"])
        limit_down = float(overview.get("limit_down_count") or 0)
        sentiment = clamp((limit_up - 40) / 5.0, -10, 12) - clamp(limit_down / 8.0, 0, 8)
        score += sentiment
        parts["sentiment"] = round(sentiment, 2)
        parts["limit_up_count"] = int(limit_up)
        parts["limit_down_count"] = None if overview.get("limit_down_count") is None else int(limit_down)
        parts["sentiment_trade_date"] = overview.get("trade_date") or ""
    if sector and sector.get("pct") is not None:
        available = True
        sector_delta = clamp(float(sector["pct"]), -5, 5) * 2.0
        score += sector_delta
        parts["sector"] = round(sector_delta, 2)
        parts["sector_name"] = sector.get("name") or ""
        parts["sector_pct"] = sector.get("pct")
    capital = _capital_points(snapshot or {})
    if capital is not None:
        available = True
        score += capital
        parts["capital"] = round(capital, 2)
    return {"score": round(clamp(score, 0, 100), 2), "available": available, "parts": parts}


def _capital_points(snapshot: dict[str, Any]) -> Optional[float]:
    volume_ratio = to_number(snapshot.get("volume_ratio"))
    turnover = to_number(snapshot.get("turnover_rate"))
    amount = to_number(snapshot.get("amount"))
    if volume_ratio is None and turnover is None and amount is None:
        return None
    points = 0.0
    if volume_ratio is not None:
        if volume_ratio >= 2:
            points += 4
        elif volume_ratio >= 1.3:
            points += 2
        elif volume_ratio < 0.6:
            points -= 2
    if turnover is not None:
        if 2 <= turnover <= 10:
            points += 2
        elif turnover > 18:
            points -= 3
    if amount is not None and amount >= 1_000_000_000:
        points += 2
    return clamp(points, -6, 8)


def _sector_leaders(boards: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    industries = [row for row in boards if row.get("board_type") != "concept" and row.get("pct") is not None]
    industries.sort(key=lambda row: row.get("pct") or 0, reverse=True)
    leaders = []
    for row in industries[:limit]:
        leaders.append(
            {
                "name": row.get("name"),
                "pct": row.get("pct"),
                "amount": row.get("amount"),
                "source": row.get("source") or "",
            }
        )
    return leaders


def _public_market_overview(market: dict[str, Any]) -> dict[str, Any]:
    return {
        "available": bool(market.get("available")),
        "source": market.get("source") or "",
        "trade_date": market.get("trade_date") or "",
        "limit_up_count": market.get("limit_up_count"),
        "limit_down_count": market.get("limit_down_count"),
        "amount": market.get("amount"),
        "note": market.get("note") or "",
    }


def _provider_call(provider: Any, name: str, default: Any, *args: Any) -> Any:
    fn = getattr(provider, name, None)
    if fn is None:
        return default
    return _safe_call(lambda: fn(*args) if args else fn(), default)


def _safe_call(func, default):
    try:
        return func()
    except Exception:
        return default


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(out) else out
