"""Intraday anomaly snapshot for the A-share candidate pool.

The report repeats only figures returned by a provider. Missing sections stay
empty and are labeled unavailable. It is an observation list, not an order.
"""

from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
from typing import Any, Optional

from .clock import shanghai_now
from .config import Theme
from .macro_news import map_macro_news, match_sector_for_theme, recency_weight
from .providers.common import format_money, pct_fmt, to_number
from .scoring import _safe_call


def build_intraday_report(
    themes: list[Theme],
    provider: Any,
    *,
    report_date: Optional[date] = None,
    now: Optional[datetime] = None,
    top_sectors: int = 8,
    move_threshold: float = 5.0,
    volume_ratio_threshold: float = 2.0,
    policy_hours: float = 18.0,
    max_anomalies: int = 30,
) -> dict[str, Any]:
    moment = shanghai_now(now)
    session_date = report_date or moment.date()
    warnings: list[str] = []
    if session_date != moment.date():
        warnings.append("盘中报告使用当前可得行情，不是该历史日期的回放。")

    market = _call(provider, "market_overview", {"available": False}) or {"available": False}
    if not market.get("available"):
        warnings.append("两市成交额或涨停/跌停家数暂不可用。")
    warnings.extend(str(item) for item in (market.get("warnings") or []) if item)

    boards = _call(provider, "sector_boards", [], top_sectors) or []
    if not boards:
        warnings.append("板块涨幅暂不可用。")
    sectors = _sector_section(boards, themes, top_sectors)

    news = _call(provider, "macro_news", [], 40) or []
    mapped = map_macro_news(news, themes, asof=moment)
    if mapped.get("stale"):
        warnings.append("政策快讯使用了过期缓存。")
    flashes = _policy_flashes(mapped.get("items") or [], themes, moment, policy_hours)

    anomalies = _candidate_anomalies(
        themes,
        provider,
        move_threshold=move_threshold,
        volume_ratio_threshold=volume_ratio_threshold,
        max_anomalies=max_anomalies,
        warnings=warnings,
    )
    sections = [market.get("available"), sectors["status"] == "ok", bool(anomalies["rows"]) or anomalies["status"] == "empty", flashes["status"] != "unavailable"]
    if all(sections):
        status = "ok"
    elif any(market.get("available") or sectors["status"] == "ok" or anomalies["rows"] or flashes["items"]):
        status = "partial"
    else:
        status = "unavailable"

    return {
        "kind": "intraday",
        "date": session_date.isoformat(),
        "generated_at": moment.isoformat(),
        "session": session_name(moment),
        "session_label": SESSION_LABELS[session_name(moment)],
        "status": status,
        "risk_note": "盘中异动只用于观察和复盘，不是买卖指令。涨停、放量和政策标题都可能滞后、遗漏或在临近收盘后失真。",
        "market": _public_market(market),
        "sectors": sectors,
        "anomalies": anomalies,
        "policy_flashes": flashes,
        "thresholds": {
            "move_pct": move_threshold,
            "volume_ratio": volume_ratio_threshold,
            "policy_hours": policy_hours,
        },
        "warnings": _unique(warnings),
    }


def render_intraday_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# 盘中异动观察 - {result['date']} {result.get('session_label', '')}",
        "",
        f"> {result.get('risk_note', '')}",
        "",
        f"状态：{result.get('status', 'unknown')}。生成时间 {result.get('generated_at', '')}。",
        "",
    ]
    if result.get("warnings"):
        lines.append("降级说明：")
        for warning in result["warnings"]:
            lines.append(f"- {warning}")
        lines.append("")

    market = result.get("market") or {}
    lines.extend(["## 市场概况", ""])
    if not market.get("available"):
        lines.append("两市成交额、涨停家数暂不可用。")
    else:
        lines.append(
            "，".join(
                [
                    f"涨停 { _count(market.get('limit_up_count')) }",
                    f"跌停 { _count(market.get('limit_down_count')) }",
                    f"上证+深证成交额 {format_money(market.get('amount'))}",
                    f"涨停池日期 {market.get('trade_date') or '未知'}",
                    f"来源 {market.get('source') or '未知'}",
                ]
            )
            + "。"
        )
        if market.get("note"):
            lines.append("")
            lines.append(str(market["note"]))
        for index in market.get("indices") or []:
            lines.append(f"- {index.get('name')} {pct_fmt(index.get('pct'))}，成交额 {format_money(index.get('amount'))}")
    lines.append("")

    sectors = result.get("sectors") or {}
    lines.extend(["## 板块涨幅", ""])
    if sectors.get("status") != "ok":
        lines.append("板块涨幅暂不可用。")
    else:
        lines.append("| 方向 | 板块 | 涨跌 | 成交额 | 上涨/成分 | 领涨 | 映射主题 |")
        lines.append("| --- | --- | ---: | ---: | --- | --- | --- |")
        for row in sectors.get("leaders") or []:
            lines.append(_sector_row("领涨", row))
        for row in sectors.get("laggards") or []:
            lines.append(_sector_row("落后", row))
        if sectors.get("concept_leaders"):
            lines.append("")
            lines.append("概念板块：")
            for row in sectors["concept_leaders"]:
                lines.append(f"- {row.get('name')} {pct_fmt(row.get('pct'))}，映射 {'、'.join(row.get('themes') or []) or '未映射'}")
    lines.append("")

    anomalies = result.get("anomalies") or {}
    lines.extend(["## 候选池异动", ""])
    rows = anomalies.get("rows") or []
    if not rows:
        lines.append(anomalies.get("message") or "候选池内没有达到阈值的波动或放量。")
    else:
        lines.append("| 代码 | 名称 | 主题 | 涨跌 | 量比 | 换手 | 成交额 | 标记 | 行情时间 |")
        lines.append("| --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |")
        for row in rows:
            flags = "、".join(FLAG_LABELS.get(flag, flag) for flag in row.get("flags") or [])
            lines.append(
                "| "
                + " | ".join(
                    [
                        row.get("code", ""),
                        _cell(row.get("name", "")),
                        _cell("、".join(row.get("themes") or [])),
                        pct_fmt(row.get("pct")),
                        _ratio(row.get("volume_ratio")),
                        _ratio(row.get("turnover_rate"), suffix="%"),
                        format_money(row.get("amount")),
                        flags,
                        _cell(" ".join(part for part in [row.get("pct_date"), row.get("snapshot_time")] if part)),
                    ]
                )
                + " |"
            )
    lines.append("")

    flashes = result.get("policy_flashes") or {}
    lines.extend(["## 政策快讯", ""])
    items = flashes.get("items") or []
    if not items:
        lines.append(flashes.get("message") or "窗口内没有新的宏观/政策快讯。")
    else:
        for item in items:
            tag = "突发 " if item.get("breaking") else ""
            labels = "、".join(item.get("category_labels") or [])
            themes = "、".join(item.get("themes") or [])
            extra = "；".join(part for part in [labels, themes] if part)
            lines.append(f"- {tag}{item.get('time', '')} {item.get('title', '')}" + (f"（{extra}）" if extra else ""))
    lines.append("")
    lines.append("以上是研究观察，不是无条件买入或卖出指令。")
    lines.append("")
    return "\n".join(lines)


def write_intraday_outputs(result: dict[str, Any], markdown: str, output_dir: str | Path) -> tuple[Path, Path]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = shanghai_now(datetime.fromisoformat(result["generated_at"])).strftime("%H%M")
    prefix = f"{result['date']}-intraday-{stamp}"
    md_path = out_dir / f"{prefix}.md"
    json_path = out_dir / f"{prefix}.json"
    md_path.write_text(markdown, encoding="utf-8")
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    json_path.write_text(payload, encoding="utf-8")
    (out_dir / "intraday-latest.md").write_text(markdown, encoding="utf-8")
    (out_dir / "intraday-latest.json").write_text(payload, encoding="utf-8")
    return md_path, json_path


SESSION_LABELS = {
    "morning": "上午连续竞价",
    "afternoon": "下午连续竞价",
    "preopen": "开盘前",
    "closed": "已收盘或非交易时段",
}

FLAG_LABELS = {
    "limit_up": "涨停",
    "limit_down": "跌停",
    "large_up": "大涨",
    "large_down": "大跌",
    "volume_spike": "放量",
    "active_turnover": "高换手",
}


def session_name(now: Optional[datetime] = None) -> str:
    moment = shanghai_now(now)
    if moment.weekday() >= 5:
        return "closed"
    minutes = moment.hour * 60 + moment.minute
    if 9 * 60 + 30 <= minutes <= 11 * 60 + 30:
        return "morning"
    if 13 * 60 <= minutes <= 15 * 60:
        return "afternoon"
    if 9 * 60 <= minutes < 9 * 60 + 30:
        return "preopen"
    return "closed"


def limit_pct_threshold(code: str, name: str) -> float:
    label = str(name or "").upper()
    if "ST" in label:
        return 4.9
    padded = str(code or "").zfill(6)
    if padded.startswith(("300", "301", "688", "689")):
        return 19.5
    if padded.startswith(("8", "4")) or padded.startswith("92"):
        return 29.5
    return 9.8


def anomaly_flags(
    snapshot: dict[str, Any],
    *,
    move_threshold: float = 5.0,
    volume_ratio_threshold: float = 2.0,
) -> list[str]:
    pct = to_number(snapshot.get("pct"))
    if pct is None:
        return []
    flags: list[str] = []
    limit = limit_pct_threshold(str(snapshot.get("code") or ""), str(snapshot.get("name") or ""))
    if pct >= limit:
        flags.append("limit_up")
    elif pct <= -limit:
        flags.append("limit_down")
    if pct >= move_threshold:
        flags.append("large_up")
    elif pct <= -move_threshold:
        flags.append("large_down")
    volume_ratio = to_number(snapshot.get("volume_ratio"))
    turnover = to_number(snapshot.get("turnover_rate"))
    if volume_ratio is not None and volume_ratio >= volume_ratio_threshold:
        flags.append("volume_spike")
    elif turnover is not None and turnover >= 8 and abs(pct) >= 3:
        flags.append("active_turnover")
    return flags


def _candidate_anomalies(
    themes: list[Theme],
    provider: Any,
    *,
    move_threshold: float,
    volume_ratio_threshold: float,
    max_anomalies: int,
    warnings: list[str],
) -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = {}
    for theme in themes:
        for candidate in theme.candidates:
            slot = grouped.setdefault(candidate.code, {"candidate": candidate, "themes": []})
            slot["themes"].append(theme.name)
    codes = list(grouped)
    quotes = _quote_map(provider, codes, warnings)
    rows = []
    scanned = 0
    for code, slot in grouped.items():
        snapshot = quotes.get(code)
        if not snapshot:
            continue
        scanned += 1
        flags = anomaly_flags(snapshot, move_threshold=move_threshold, volume_ratio_threshold=volume_ratio_threshold)
        if not flags:
            continue
        candidate = slot["candidate"]
        rows.append(
            {
                "code": code,
                "name": snapshot.get("name") or candidate.name,
                "themes": slot["themes"],
                "pct": to_number(snapshot.get("pct")),
                "price": to_number(snapshot.get("price")),
                "amount": to_number(snapshot.get("amount")),
                "turnover_rate": to_number(snapshot.get("turnover_rate")),
                "volume_ratio": to_number(snapshot.get("volume_ratio")),
                "flags": flags,
                "pct_source": snapshot.get("pct_source") or "",
                "pct_date": snapshot.get("pct_date") or "",
                "snapshot_time": snapshot.get("snapshot_time") or "",
                "note": "观察异动，不是买卖指令。",
            }
        )
    rows.sort(key=lambda row: (_severity(row["flags"]), abs(row.get("pct") or 0), row.get("volume_ratio") or 0), reverse=True)
    if not codes:
        status = "empty"
        message = "配置里没有候选股。"
    elif scanned == 0:
        status = "unavailable"
        message = "候选池行情暂不可用。"
    elif not rows:
        status = "empty"
        message = "候选池内没有达到阈值的波动或放量。"
    else:
        status = "ok"
        message = ""
    return {"status": status, "message": message, "scanned": scanned, "rows": rows[:max_anomalies]}


def _quote_map(provider: Any, codes: list[str], warnings: list[str]) -> dict[str, dict[str, Any]]:
    batch = getattr(provider, "quote_candidates", None)
    if batch is not None:
        quoted = _safe_call(lambda: batch(codes), {}) or {}
        if quoted:
            return {str(code).zfill(6): row for code, row in quoted.items()}
        warnings.append("批量行情不可用，改为逐只快照。")
    single = getattr(provider, "a_snapshot", None)
    if single is None:
        warnings.append("没有可用的行情接口。")
        return {}
    out = {}
    for code in codes[:40]:
        snapshot = _safe_call(lambda c=code: single(c), {}) or {}
        if snapshot.get("pct") is not None or snapshot.get("price") is not None:
            snapshot = dict(snapshot)
            snapshot["code"] = str(code).zfill(6)
            out[snapshot["code"]] = snapshot
    if len(codes) > 40:
        warnings.append("逐只快照只覆盖了前 40 只候选，避免请求过慢。")
    return out


def _sector_section(boards: list[dict[str, Any]], themes: list[Theme], top_sectors: int) -> dict[str, Any]:
    if not boards:
        return {"status": "unavailable", "source": "", "leaders": [], "laggards": [], "concept_leaders": []}
    decorated = [_decorate_board(board, themes) for board in boards]
    industries = [row for row in decorated if row.get("board_type") != "concept" and row.get("pct") is not None]
    concepts = [row for row in decorated if row.get("board_type") == "concept" and row.get("pct") is not None]
    concepts.sort(key=lambda row: row.get("pct") or 0, reverse=True)
    tagged = any(row.get("rank_side") for row in industries)
    if tagged:
        leaders = [row for row in industries if row.get("rank_side") != "laggard"]
        laggards = [row for row in industries if row.get("rank_side") == "laggard"]
        leaders.sort(key=lambda row: row.get("pct") or 0, reverse=True)
        laggards.sort(key=lambda row: row.get("pct") or 0)
    else:
        industries.sort(key=lambda row: row.get("pct") or 0, reverse=True)
        leaders = list(industries)
        laggards = [row for row in industries if (row.get("pct") or 0) < 0]
    leaders = leaders[:top_sectors]
    laggards = [row for row in laggards if row not in leaders][:5]
    return {
        "status": "ok" if leaders or concepts else "unavailable",
        "source": (decorated[0].get("source") if decorated else "") or "",
        "leaders": leaders,
        "laggards": laggards,
        "concept_leaders": concepts[:5],
    }


def _decorate_board(board: dict[str, Any], themes: list[Theme]) -> dict[str, Any]:
    matched = []
    for theme in themes:
        hit = match_sector_for_theme(theme, [board])
        if hit and hit.get("name") == board.get("name"):
            matched.append(theme.name)
    row = dict(board)
    row["themes"] = matched
    return row


def _policy_flashes(items: list[dict[str, Any]], themes: list[Theme], moment: datetime, policy_hours: float) -> dict[str, Any]:
    flashes = []
    for item in items:
        parsed_weight = recency_weight(item.get("time"), moment)
        age = _age_hours(item.get("time"), moment)
        if age is None:
            if parsed_weight <= 0:
                continue
            age = policy_hours
        if age < -1 or age > policy_hours:
            continue
        if not item.get("categories") and not item.get("broad"):
            continue
        themes_hit = []
        text = f"{item.get('title', '')} {item.get('summary', '')}"
        for theme in themes:
            from .macro_news import policy_keywords_for

            if any(keyword and keyword in text for keyword in policy_keywords_for(theme)):
                themes_hit.append(theme.name)
            elif theme.id == "finance_brokerage_fintech" and any(category in {"pboc", "csrc", "stabilizer"} for category in item.get("categories") or []):
                themes_hit.append(theme.name)
        row = dict(item)
        row["themes"] = themes_hit
        row["breaking"] = age <= 1.5
        flashes.append(row)
    flashes.sort(key=lambda row: str(row.get("time", "")), reverse=True)
    if not flashes:
        return {"status": "empty", "message": "窗口内没有新的宏观/政策快讯。", "items": []}
    return {"status": "ok", "message": "", "items": flashes[:8]}


def _public_market(market: dict[str, Any]) -> dict[str, Any]:
    return {
        "available": bool(market.get("available")),
        "source": market.get("source") or "",
        "trade_date": market.get("trade_date") or "",
        "limit_up_count": market.get("limit_up_count"),
        "limit_down_count": market.get("limit_down_count"),
        "amount": market.get("amount"),
        "indices": market.get("indices") or [],
        "note": market.get("note") or "",
    }


def _age_hours(value: object, moment: datetime) -> Optional[float]:
    from .clock import parse_cn_time

    parsed = parse_cn_time(value)
    if parsed is None:
        return None
    return (moment - parsed).total_seconds() / 3600


def _call(provider: Any, name: str, default: Any, *args: Any) -> Any:
    fn = getattr(provider, name, None)
    if fn is None:
        return default
    return _safe_call(lambda: fn(*args) if args else fn(), default)


def _severity(flags: list[str]) -> int:
    score = 0
    if "limit_up" in flags or "limit_down" in flags:
        score += 3
    if "large_up" in flags or "large_down" in flags:
        score += 2
    if "volume_spike" in flags or "active_turnover" in flags:
        score += 1
    return score


def _sector_row(direction: str, row: dict[str, Any]) -> str:
    breadth = ""
    if row.get("up_count") is not None and row.get("member_count") is not None:
        breadth = f"{row['up_count']}/{row['member_count']}"
    leader = row.get("leader_name") or ""
    if row.get("leader_pct") is not None:
        leader = f"{leader} {pct_fmt(row.get('leader_pct'))}".strip()
    return (
        f"| {direction} | {_cell(row.get('name', ''))} | {pct_fmt(row.get('pct'))} | {format_money(row.get('amount'))} | "
        f"{breadth or '未知'} | {_cell(leader or '未知')} | {_cell('、'.join(row.get('themes') or []) or '未映射')} |"
    )


def _count(value: Any) -> str:
    return "暂无" if value is None else str(value)


def _ratio(value: Any, suffix: str = "") -> str:
    number = to_number(value)
    if number is None:
        return "未知"
    return f"{number:.2f}{suffix}"


def _cell(value: Any) -> str:
    return str(value).replace("|", "/").replace("\n", " ").strip()


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out
