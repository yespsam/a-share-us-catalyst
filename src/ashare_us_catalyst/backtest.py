from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import date, timedelta
from typing import Any, Protocol

import numpy as np
import pandas as pd

from .config import Candidate, Theme
from .providers.common import pct_fmt, serialize_kline, to_number
from .scoring import (
    analyst_profile,
    clamp,
    historical_stats,
    score_candidate,
)
from .us_quality import (
    UsQualityCandidate,
    calculate_risk_penalty,
    conviction_for,
    rating_for,
    risk_gate_for as us_risk_gate_for,
    technical_metrics,
)


class BacktestProvider(Protocol):
    def us_history(self, ticker: str, start: date, end: date) -> pd.DataFrame: ...

    def a_history(self, code: str, start: date, end: date) -> pd.DataFrame: ...


def run_backtest(
    themes: list[Theme],
    us_universe: list[UsQualityCandidate],
    provider: BacktestProvider,
    *,
    report_date: date,
    window_days: int = 182,
    lookback_days: int = 260,
    top_n: int = 5,
) -> dict[str, Any]:
    start = report_date - timedelta(days=window_days + lookback_days + 20)
    ashare = backtest_ashare(themes, provider, report_date=report_date, start=start, window_days=window_days, lookback_days=lookback_days, top_n=top_n)
    us = backtest_us_quality(us_universe, provider, report_date=report_date, start=start, window_days=window_days, lookback_days=lookback_days, top_n=10)
    return {
        "date": str(report_date),
        "generated_at": pd.Timestamp.now(tz="Asia/Shanghai").isoformat(),
        "window_days": window_days,
        "lookback_days": lookback_days,
        "method": {
            "ashare": "Each backtest day uses only prior A-share K-line data and the latest completed US session; historical news is neutral because point-in-time news archives are not available.",
            "us": "US quality backtest uses prior daily K-lines plus configured quality/growth/valuation/moat inputs, then measures forward close-to-close returns.",
            "target": "Forward 1/3/5 trading-day close-to-close returns; this approximates a 9:00 research recommendation and is not an executable open-price fill.",
        },
        "ashare": ashare,
        "us": us,
    }


def backtest_ashare(
    themes: list[Theme],
    provider: BacktestProvider,
    *,
    report_date: date,
    start: date,
    window_days: int,
    lookback_days: int,
    top_n: int,
) -> dict[str, Any]:
    test_start = report_date - timedelta(days=window_days)
    us_histories = {
        ticker.ticker: _safe_history(lambda t=ticker.ticker: provider.us_history(t, start, report_date))
        for theme in themes
        for ticker in theme.us_tickers
    }
    candidates = {candidate.code: candidate for theme in themes for candidate in theme.candidates}
    a_histories = {code: _safe_history(lambda c=code: provider.a_history(c, start, report_date)) for code in candidates}

    all_trades: list[dict[str, Any]] = []
    baseline: list[float] = []
    by_theme: list[dict[str, Any]] = []

    for theme in themes:
        theme_series = _historical_theme_series_from_frames(theme, us_histories)
        theme_trades: list[dict[str, Any]] = []
        test_dates = _candidate_test_dates([a_histories.get(candidate.code) for candidate in theme.candidates], test_start, report_date)

        for current_date in test_dates:
            signal = _theme_signal_at(theme, us_histories, current_date - timedelta(days=1))
            if signal["weight_sum"] == 0:
                continue
            scored: list[dict[str, Any]] = []
            day_baseline: list[float] = []
            for candidate in theme.candidates:
                hist = a_histories.get(candidate.code)
                if hist is None or hist.empty:
                    continue
                returns = _forward_returns(hist, current_date)
                if returns is None:
                    continue
                day_baseline.append(returns["return_1d"])
                train = _training_window(hist, current_date, lookback_days)
                if len(train) < 40:
                    continue
                train_theme = theme_series[theme_series["date"] < pd.Timestamp(current_date)]
                stats = historical_stats(train, train_theme)
                prev = train.iloc[-1]
                snapshot = _snapshot_from_history(candidate, prev)
                total, factors = score_candidate(signal, stats, snapshot, 0.0, candidate)
                analyst = analyst_profile(total, signal, stats, snapshot, 0.0, [], [], candidate)
                scored.append(
                    {
                        "date": str(current_date),
                        "code": candidate.code,
                        "name": candidate.name,
                        "theme": theme.name,
                        "score": round(total, 2),
                        "rating": analyst["rating"],
                        "conviction": analyst["conviction"],
                        "risk_gate": analyst["risk_gate"],
                        "factors": factors,
                        **returns,
                    }
                )
            if day_baseline:
                baseline.extend(day_baseline)
            scored.sort(key=lambda item: item["score"], reverse=True)
            selected = scored[:top_n]
            all_trades.extend(selected)
            theme_trades.extend(selected)

        by_theme.append({"theme": theme.name, **_summarize_trades(theme_trades, [])})

    summary = _summarize_trades(all_trades, baseline)
    recent = sorted(all_trades, key=lambda item: item["date"], reverse=True)[:18]
    return {
        "summary": summary,
        "by_theme": by_theme,
        "recent_signals": recent,
        "data": {
            "candidate_count": len(candidates),
            "theme_count": len(themes),
            "news_mode": "neutral_point_in_time_news_unavailable",
            "weight_profile": "legacy",
            "weight_note": "历史逐日的政策、涨停情绪和板块资金无法稳定复原，回测保持旧权重。",
        },
    }


def backtest_us_quality(
    universe: list[UsQualityCandidate],
    provider: BacktestProvider,
    *,
    report_date: date,
    start: date,
    window_days: int,
    lookback_days: int,
    top_n: int,
) -> dict[str, Any]:
    test_start = report_date - timedelta(days=window_days)
    histories = {item.ticker: _safe_history(lambda t=item.ticker: provider.us_history(t, start, report_date)) for item in universe}
    test_dates = _candidate_test_dates(list(histories.values()), test_start, report_date)
    all_trades: list[dict[str, Any]] = []
    baseline: list[float] = []

    for current_date in test_dates:
        scored: list[dict[str, Any]] = []
        day_baseline: list[float] = []
        for item in universe:
            hist = histories.get(item.ticker)
            if hist is None or hist.empty:
                continue
            returns = _forward_returns(hist, current_date)
            if returns is None:
                continue
            day_baseline.append(returns["return_1d"])
            train = _training_window(hist, current_date, lookback_days)
            if len(train) < 40:
                continue
            row = _score_us_from_history(item, train)
            scored.append(
                {
                    "date": str(current_date),
                    "ticker": item.ticker,
                    "name": item.name,
                    "sector": item.sector,
                    **row,
                    **returns,
                }
            )
        if day_baseline:
            baseline.extend(day_baseline)
        scored.sort(key=lambda item: item["score"], reverse=True)
        all_trades.extend(scored[:top_n])

    by_sector = []
    for sector in sorted({trade["sector"] for trade in all_trades}):
        sector_trades = [trade for trade in all_trades if trade["sector"] == sector]
        by_sector.append({"sector": sector, **_summarize_trades(sector_trades, [])})
    by_sector.sort(key=lambda item: item.get("avg_return_3d") or -999, reverse=True)

    return {
        "summary": _summarize_trades(all_trades, baseline),
        "by_sector": by_sector,
        "recent_signals": sorted(all_trades, key=lambda item: item["date"], reverse=True)[:18],
        "data": {"candidate_count": len(universe)},
    }


def _score_us_from_history(item: UsQualityCandidate, train: pd.DataFrame) -> dict[str, Any]:
    prev = train.iloc[-1]
    quote = {"price": to_number(prev.get("close")), "pct": to_number(prev.get("pct"))}
    metrics = technical_metrics(train, quote)
    quality_component = item.quality * 0.24
    growth_component = item.growth * 0.18
    valuation_component = item.valuation * 0.14
    moat_component = item.moat * 0.16
    catalyst_component = item.catalyst * 0.12
    trend_component = metrics["trend_score"] * 0.10
    earnings_momentum_component = metrics["earnings_momentum_score"] * 0.08
    penalty = calculate_risk_penalty(item, metrics)
    score = clamp(
        quality_component
        + growth_component
        + valuation_component
        + moat_component
        + catalyst_component
        + trend_component
        + earnings_momentum_component
        - penalty,
        0,
        100,
    )
    risk_gate = us_risk_gate_for(item, metrics, penalty)
    conviction = conviction_for(score, item, metrics, penalty, risk_gate)
    rating = rating_for(score, metrics, risk_gate, conviction)
    return {
        "score": round(score, 2),
        "rating": rating,
        "conviction": round(conviction, 1),
        "risk_gate": risk_gate,
        "kline": serialize_kline(train, limit=60),
    }


def _historical_theme_series_from_frames(theme: Theme, histories: dict[str, pd.DataFrame]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for ticker in theme.us_tickers:
        hist = histories.get(ticker.ticker)
        if hist is None or hist.empty:
            continue
        frame = hist[["date", "pct"]].dropna().copy()
        frame["weighted_pct"] = pd.to_numeric(frame["pct"], errors="coerce") * ticker.weight
        frame["weight"] = ticker.weight
        frames.append(frame[["date", "weighted_pct", "weight"]])
    if not frames:
        return pd.DataFrame(columns=["date", "theme_pct"])
    raw = pd.concat(frames, ignore_index=True)
    grouped = raw.groupby("date", as_index=False).agg(weighted_pct=("weighted_pct", "sum"), weight=("weight", "sum"))
    grouped["theme_pct"] = grouped["weighted_pct"] / grouped["weight"].replace(0, np.nan)
    return grouped[["date", "theme_pct"]].dropna().sort_values("date")


def _theme_signal_at(theme: Theme, histories: dict[str, pd.DataFrame], cutoff: date) -> dict[str, Any]:
    quotes: list[dict[str, Any]] = []
    weighted_sum = 0.0
    weight_sum = 0.0
    positive_weight = 0.0
    for ticker in theme.us_tickers:
        hist = histories.get(ticker.ticker)
        if hist is None or hist.empty:
            continue
        eligible = hist[hist["date"] <= pd.Timestamp(cutoff)].dropna(subset=["pct"])
        if eligible.empty:
            continue
        latest = eligible.iloc[-1]
        pct = to_number(latest.get("pct"))
        if pct is None:
            continue
        quotes.append({"ticker": ticker.ticker, "pct": pct, "weight": ticker.weight})
        weighted_sum += pct * ticker.weight
        weight_sum += ticker.weight
        if pct > 0:
            positive_weight += ticker.weight
    avg_pct = weighted_sum / weight_sum if weight_sum else 0.0
    breadth = positive_weight / weight_sum if weight_sum else 0.0
    score = clamp(50 + avg_pct * 9 + breadth * 10, 0, 100)
    quotes.sort(key=lambda item: item["pct"], reverse=True)
    summary = "，".join(f"{item['ticker']} {pct_fmt(item['pct'])}" for item in quotes[:5]) or "无可用历史信号"
    return {"avg_pct": round(avg_pct, 3), "score": round(score, 2), "breadth": round(breadth, 3), "quotes": quotes, "summary": summary, "weight_sum": round(weight_sum, 3)}


def _candidate_test_dates(histories: list[pd.DataFrame | None], test_start: date, report_date: date) -> list[date]:
    dates: set[date] = set()
    for hist in histories:
        if hist is None or hist.empty:
            continue
        frame = hist[(hist["date"] >= pd.Timestamp(test_start)) & (hist["date"] <= pd.Timestamp(report_date))]
        dates.update(pd.Timestamp(value).date() for value in frame["date"].tolist())
    return sorted(dates)


def _training_window(hist: pd.DataFrame, current_date: date, lookback_days: int) -> pd.DataFrame:
    start = pd.Timestamp(current_date - timedelta(days=lookback_days + 20))
    end = pd.Timestamp(current_date)
    return hist[(hist["date"] >= start) & (hist["date"] < end)].copy()


def _snapshot_from_history(candidate: Candidate, row: pd.Series) -> dict[str, Any]:
    return {
        "code": candidate.code,
        "name": candidate.name,
        "industry": candidate.industry,
        "price": to_number(row.get("close")),
        "pct": to_number(row.get("pct")),
        "turnover_rate": to_number(row.get("turnover_rate")),
    }


def _forward_returns(hist: pd.DataFrame, current_date: date) -> dict[str, float] | None:
    forward = hist[hist["date"] >= pd.Timestamp(current_date)].dropna(subset=["pct"]).head(5)
    if len(forward) < 5:
        return None
    values = pd.to_numeric(forward["pct"], errors="coerce").dropna().to_numpy(dtype=float)
    if len(values) < 5:
        return None
    return {
        "return_1d": round(float(values[0]), 4),
        "return_3d": round(_compound(values[:3]), 4),
        "return_5d": round(_compound(values[:5]), 4),
    }


def _compound(values: np.ndarray) -> float:
    return (float(np.prod(1 + values / 100)) - 1) * 100


def _summarize_trades(trades: list[dict[str, Any]], baseline: list[float]) -> dict[str, Any]:
    returns_1d = [trade["return_1d"] for trade in trades if trade.get("return_1d") is not None]
    returns_3d = [trade["return_3d"] for trade in trades if trade.get("return_3d") is not None]
    returns_5d = [trade["return_5d"] for trade in trades if trade.get("return_5d") is not None]
    rating_counts = Counter(str(trade.get("rating", "Unknown")) for trade in trades)
    gate_counts = Counter(str(trade.get("risk_gate", "Unknown")) for trade in trades)
    baseline_avg = _mean(baseline)
    avg_1d = _mean(returns_1d)
    return {
        "trade_count": len(trades),
        "day_count": len({trade.get("date") for trade in trades}),
        "hit_rate_1d": _hit_rate(returns_1d),
        "hit_rate_3d": _hit_rate(returns_3d),
        "hit_rate_5d": _hit_rate(returns_5d),
        "avg_return_1d": avg_1d,
        "avg_return_3d": _mean(returns_3d),
        "avg_return_5d": _mean(returns_5d),
        "median_return_3d": _median(returns_3d),
        "worst_return_5d": _min(returns_5d),
        "best_return_5d": _max(returns_5d),
        "baseline_return_1d": baseline_avg,
        "excess_return_1d": round(avg_1d - baseline_avg, 4) if avg_1d is not None and baseline_avg is not None else None,
        "rating_counts": dict(rating_counts),
        "risk_gate_counts": dict(gate_counts),
    }


def _hit_rate(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(1 for value in values if value > 0) / len(values) * 100, 2)


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(float(np.mean(values)), 4)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return round(float(np.median(values)), 4)


def _min(values: list[float]) -> float | None:
    return round(float(min(values)), 4) if values else None


def _max(values: list[float]) -> float | None:
    return round(float(max(values)), 4) if values else None


def _safe_history(func) -> pd.DataFrame:
    try:
        return func()
    except Exception:
        return pd.DataFrame(columns=["date", "close", "pct"])
