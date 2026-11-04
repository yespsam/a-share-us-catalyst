from __future__ import annotations

from pathlib import Path
from typing import Any, Tuple, Union
import json

from .providers.common import pct_fmt


def render_markdown(result: dict[str, Any], risk_note: str) -> str:
    lines: list[str] = []
    lines.append(f"# 美股映射 A 股早报 - {result['date']}")
    lines.append("")
    lines.append(f"> {risk_note}")
    lines.append("")
    scoring = result.get("scoring") or {}
    if scoring:
        lines.append(f"评分口径：{scoring.get('label', '')}。{scoring.get('note', '')}")
        if scoring.get("fallback"):
            lines.append("")
            lines.append(f"降级：{scoring['fallback']}")
        lines.append("")
    lines.extend(_macro_lines(result))
    lines.append("## 总览")
    lines.append("")
    for block in result["themes"][:6]:
        signal = block["signal"]
        theme = block["theme"]
        lines.append(f"- {theme['name']}：美股主题均值 {pct_fmt(signal['avg_pct'])}，信号分 {signal['score']:.1f}；{signal['summary']}")
    lines.append("")

    for block in result["themes"]:
        theme = block["theme"]
        signal = block["signal"]
        lines.append(f"## {theme['name']}")
        lines.append("")
        lines.append(f"美股触发：{signal['summary']}。主题信号均值 {pct_fmt(signal['avg_pct'])}，信号分 {signal['score']:.1f}。")
        lines.append("")
        lines.append(f"映射逻辑：{theme['logic']}")
        china_line = _theme_china_line(block)
        if china_line:
            lines.append("")
            lines.append(china_line)
        lines.append("")
        lines.append(
            "| 排名 | 代码 | 名称 | 评级 | Conviction | Risk Gate | 产业 | 市值 | 当日涨跌 | 综合分 | Entry Plan | 利好逻辑 | 近期重大新闻 |"
        )
        lines.append("| --- | --- | --- | --- | ---: | --- | --- | --- | --- | ---: | --- | --- | --- |")
        for idx, item in enumerate(block["top"], start=1):
            f = item["formatted"]
            analyst = item.get("analyst", {})
            lines.append(
                f"| {idx} | {f['code']} | {f['name']} | {analyst.get('rating', 'Neutral')} | "
                f"{analyst.get('conviction', '-')} | {analyst.get('risk_gate', 'Watch')} | {f['industry']} | {f['market_cap']} | "
                f"{_change_cell(f)} | {f['score']} | {_cell(analyst.get('entry_plan', f['rationale']))} | "
                f"{_cell(f['rationale'])} | {_cell(f['news'])} |"
            )
        lines.append("")
        lines.append("分析师评分拆解：")
        for idx, item in enumerate(block["top"], start=1):
            f = item["formatted"]
            factors = item["factors"]
            analyst = item.get("analyst", {})
            dimensions = analyst.get("dimensions", {})
            lines.append(
                f"- {idx}. {f['code']} {f['name']}：评级 {analyst.get('rating', 'Neutral')}，"
                f"Conviction {analyst.get('conviction', '-')}，Risk Gate {analyst.get('risk_gate', 'Watch')}；"
                f"催化 {dimensions.get('catalyst', '-')}，历史优势 {dimensions.get('history_edge', '-')}，"
                f"质量代理 {dimensions.get('quality_proxy', '-')}，动量 {dimensions.get('momentum', '-')}，"
                f"新闻 {dimensions.get('news', '-')}，"
                f"中国催化 {dimensions.get('china_catalyst', '-')}，风险质量 {dimensions.get('risk', '-')}；"
                f"原始因子：信号 {factors['signal']}，历史 {factors['history']}，"
                f"动量 {factors['momentum']}，新闻 {factors['news']}，"
                f"中国催化 {factors.get('china_catalyst', 0)}，风险扣分 {factors['risk_penalty']}。"
            )
            scenario = analyst.get("scenario")
            if scenario:
                lines.append(
                    f"  情景：{_cell(scenario.get('bull', ''))} / {_cell(scenario.get('base', ''))} / {_cell(scenario.get('bear', ''))}"
                )
        lines.append("")

    lines.append("## 使用口径")
    lines.append("")
    lines.append("- 优先看 Analyst Score、Conviction、Risk Gate 是否同时靠前。")
    lines.append("- 中国本地催化是研究加权，不是买入指令。政策、涨停情绪或板块涨幅缺失时，该项保持中性；整层不可用时回退旧权重。")
    lines.append("- Buy/Outperform 只代表候选优先级，仍需结合开盘流动性、公告和仓位管理。")
    lines.append("- 若开盘直接高开过多或接近涨停，报告候选应改为观察，不建议追价。")
    lines.append("- 出现减持、处罚、立案、业绩暴雷等负面新闻时，即使排名靠前也要降级处理。")
    lines.append("- 每次交易前重新检查公告、停牌、涨跌停、流动性和仓位。")
    lines.append("")
    return "\n".join(lines)


def write_outputs(result: dict[str, Any], markdown: str, output_dir: Union[str, Path]) -> Tuple[Path, Path]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{result['date']}-morning"
    md_path = out_dir / f"{prefix}.md"
    json_path = out_dir / f"{prefix}.json"
    md_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return md_path, json_path


def _macro_lines(result: dict[str, Any]) -> list[str]:
    macro = result.get("macro") or {}
    items = macro.get("items") or []
    market = (result.get("china_market") or {}).get("overview") or {}
    warnings = (result.get("china_market") or {}).get("warnings") or []
    if not items and not market and not warnings and "macro" not in result:
        return []
    lines = ["## 宏观与政策", ""]
    if macro.get("stale"):
        lines.append("快讯来自过期缓存。")
        lines.append("")
    if not items:
        lines.append("暂无可用的宏观/政策快讯。")
    else:
        for item in items[:8]:
            labels = "、".join(item.get("category_labels") or [])
            suffix = f"（{labels}）" if labels else ""
            lines.append(f"- {item.get('time', '')} {item.get('title', '')}{suffix}")
    if market.get("available"):
        lines.append("")
        limit_up = market.get("limit_up_count")
        limit_down = market.get("limit_down_count")
        lines.append(
            f"情绪参考：涨停 {limit_up if limit_up is not None else '暂无'}，"
            f"跌停 {limit_down if limit_down is not None else '暂无'}，"
            f"日期 {market.get('trade_date') or '未知'}。"
        )
    for warning in warnings:
        lines.append(f"- 降级：{warning}")
    lines.append("")
    lines.append("政策标题来自公开快讯检索，可能滞后或遗漏，只作为研究输入。")
    lines.append("")
    return lines


def _theme_china_line(block: dict[str, Any]) -> str:
    context = block.get("china_context") or {}
    if not context:
        return ""
    parts = []
    if context.get("policy_available"):
        parts.append(f"政策分 {context.get('policy_score')}")
    sector = context.get("sector") or {}
    if sector.get("name"):
        parts.append(f"板块 {sector.get('name')} {pct_fmt(sector.get('pct'))}")
    if not parts:
        return ""
    return "中国本地催化参考：" + "，".join(parts) + "。这是映射提示，不是交易指令。"


def _cell(value: str) -> str:
    return str(value).replace("|", "/").replace("\n", " ").strip()


def _change_cell(formatted: dict[str, Any]) -> str:
    meta = " · ".join(str(part) for part in [formatted.get("day_pct_source"), formatted.get("day_pct_asof")] if part)
    value = formatted.get("day_pct", "未知")
    return _cell(f"{value}（{meta}）" if meta else value)
