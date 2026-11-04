"""China macro and policy news tagging, theme mapping, and catalyst inputs.

Headlines are matched with explicit phrases. This is a research input, not a
trading instruction and not a claim that a headline caused a price move.
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Optional

from .clock import parse_cn_time, shanghai_now
from .config import Theme


POLICY_CATEGORIES: dict[str, dict[str, Any]] = {
    "pboc": {
        "label": "央行/流动性",
        "keywords": [
            "央行",
            "人民银行",
            "货币政策",
            "降准",
            "降息",
            "加息",
            "MLF",
            "LPR",
            "逆回购",
            "公开市场",
            "存款准备金",
            "中期借贷便利",
        ],
    },
    "csrc": {
        "label": "证监会/资本市场",
        "keywords": [
            "证监会",
            "上交所",
            "深交所",
            "北交所",
            "印花税",
            "减持新规",
            "程序化交易",
            "注册制",
            "再融资",
            "资本市场",
        ],
    },
    "stabilizer": {
        "label": "稳市工具",
        "keywords": [
            "平准基金",
            "中央汇金",
            "汇金公司",
            "汇金增持",
            "证金公司",
            "国家队",
            "稳市",
            "股票回购增持再贷款",
            "回购增持再贷款",
        ],
    },
    "industrial": {
        "label": "产业政策",
        "keywords": [
            "产业政策",
            "工信部",
            "以旧换新",
            "设备更新",
            "新质生产力",
            "国产替代",
            "低空经济",
        ],
    },
    "fiscal": {
        "label": "财政/国务院",
        "keywords": [
            "财政部",
            "发改委",
            "国务院",
            "政府工作报告",
            "财政政策",
            "专项债",
            "特别国债",
            "稳增长",
            "扩大内需",
        ],
    },
}

POSITIVE_PHRASES = [
    "降准",
    "降息",
    "定向降准",
    "全面降准",
    "流动性合理充裕",
    "净投放",
    "平准基金",
    "汇金增持",
    "中央汇金",
    "以旧换新",
    "设备更新",
    "新质生产力",
    "回购增持再贷款",
    "财政加力",
    "扩大内需",
    "稳增长",
    "超长期特别国债",
    "加力",
]

NEGATIVE_PHRASES = [
    "加息",
    "上调存款准备金",
    "收紧流动性",
    "净回笼",
    "收水",
    "约谈",
    "立案调查",
    "行政处罚",
    "从严监管",
    "减持新规",
    "叫停",
    "警示函",
    "不及预期",
]

# Phrases that describe a market-wide policy impulse. Theme keyword hits still
# take priority; these only apply a smaller weight to unmapped themes.
BROAD_POSITIVE_PHRASES = [
    "降准",
    "降息",
    "平准基金",
    "汇金增持",
    "中央汇金",
    "超长期特别国债",
    "流动性合理充裕",
    "回购增持再贷款",
    "稳增长",
]
BROAD_NEGATIVE_PHRASES = ["加息", "收紧流动性", "净回笼"]

# Regulatory and liquidity categories lean on brokers even when the headline
# does not name a broker.
CATEGORY_THEME_BIAS: dict[str, dict[str, float]] = {
    "pboc": {"finance_brokerage_fintech": 0.85},
    "csrc": {"finance_brokerage_fintech": 1.0},
    "stabilizer": {"finance_brokerage_fintech": 1.0},
    "industrial": {},
    "fiscal": {},
}

# Overseas index prints often contain words like 半导体, but they are not China policy.
OVERSEAS_TAPE = ["费城半导体", "纳斯达克", "道琼斯", "标普500", "标普 500", "美股三大指数", "恒生指数", "日经", "韩国KOSPI", "韩国综指"]
FOREIGN_INSTITUTIONS = ["美联储", "欧洲央行", "欧央行", "日本央行", "英国央行", "波兰央行", "加拿大央行", "澳大利亚央行", "美国财政部", "美国劳工部"]
STRUCTURAL_CSRC = ["印花税", "减持新规", "程序化交易", "注册制", "再融资", "资本市场", "上交所", "深交所", "北交所"]
COMPANY_CASE_PHRASES = ["被证监会立案", "遭证监会立案", "证监会立案"]


def is_overseas_tape(title: str) -> bool:
    return any(token in str(title or "") for token in OVERSEAS_TAPE)


def _scrub_foreign(text: str) -> str:
    cleaned = str(text or "")
    for token in FOREIGN_INSTITUTIONS + ["全球央行"]:
        cleaned = cleaned.replace(token, "")
    cleaned = re.sub(
        r"(?:瑞典|波兰|欧洲|日本|英国|美国|加拿大|澳大利亚|瑞士|挪威|韩国|俄罗斯|法国|德国|意大利|西班牙|印度|土耳其|巴西|新西兰|新加坡)央行",
        "",
        cleaned,
    )
    return re.sub(r"(?:美国|日本|英国|德国|法国)财政部", "", cleaned)


def _policy_text(title: str, summary: str) -> str:
    return _scrub_foreign(f"{title} {summary}")


def is_company_case(title: str) -> bool:
    text = str(title or "")
    structural = any(phrase in text for phrase in STRUCTURAL_CSRC + BROAD_POSITIVE_PHRASES + BROAD_NEGATIVE_PHRASES)
    if structural:
        return False
    if any(phrase in text for phrase in COMPANY_CASE_PHRASES):
        return True
    if "证监会" in text and any(token in text for token in ("立案", "被罚", "处罚", "操纵")):
        return True
    return False


DEFAULT_THEME_POLICY_KEYWORDS: dict[str, list[str]] = {
    "ai_compute_semis": ["人工智能", "算力", "半导体", "芯片", "光模块", "集成电路", "数据中心", "国产替代"],
    "ev_battery_storage": ["新能源", "锂电池", "储能", "光伏", "新能源汽车", "动力电池", "充电桩", "以旧换新"],
    "innovative_drugs_medtech": ["创新药", "医保", "集采", "医疗器械", "生物医药"],
    "consumer_ecommerce_travel": ["促消费", "免税", "旅游", "家电", "以旧换新", "消费复苏"],
    "commodities_energy_gold": ["黄金", "有色", "原油", "煤炭", "稀土", "铜价"],
    "finance_brokerage_fintech": ["券商", "资本市场", "印花税", "证券", "汇金", "平准", "降准", "降息"],
    "robotics_industrial_auto": ["机器人", "人形机器人", "工业自动化", "智能制造", "设备更新"],
    "aerospace_defense": ["商业航天", "卫星互联网", "军工", "航空航天", "低空经济", "大飞机"],
}

# Tencent/Eastmoney industry names are shorter than news phrases.
BOARD_ALIASES: dict[str, list[str]] = {
    "ai_compute_semis": ["半导体", "电子", "通信", "光学", "计算机", "元件"],
    "ev_battery_storage": ["电池", "汽车", "电力设备", "光伏", "能源金属", "电网"],
    "innovative_drugs_medtech": ["医药", "生物", "医疗"],
    "consumer_ecommerce_travel": ["食品饮料", "商贸", "零售", "家电", "社会服务", "美容"],
    "commodities_energy_gold": ["有色", "煤炭", "石油", "钢铁", "贵金属", "黄金"],
    "finance_brokerage_fintech": ["证券", "非银", "银行", "保险"],
    "robotics_industrial_auto": ["机械", "自动化", "机器人", "工控"],
    "aerospace_defense": ["国防", "军工", "航天", "航空"],
}


def policy_keywords_for(theme: Theme) -> list[str]:
    custom = [str(item).strip() for item in (getattr(theme, "policy_keywords", ()) or []) if str(item).strip()]
    if custom:
        return custom
    if theme.id in DEFAULT_THEME_POLICY_KEYWORDS:
        return list(DEFAULT_THEME_POLICY_KEYWORDS[theme.id])
    tokens = [part.strip() for part in re.split(r"[\s/、,，]+", theme.name) if len(part.strip()) >= 2]
    return tokens


def annotate_macro_item(item: dict[str, Any]) -> dict[str, Any]:
    title = _scrub_foreign(str(item.get("title") or ""))
    text = _policy_text(str(item.get("title") or ""), str(item.get("summary") or ""))
    categories = []
    for category_id, spec in POLICY_CATEGORIES.items():
        if any(keyword in title for keyword in spec["keywords"]):
            categories.append(category_id)
    positive = sum(1 for phrase in POSITIVE_PHRASES if phrase in text)
    negative = sum(1 for phrase in NEGATIVE_PHRASES if phrase in text)
    polarity = positive * 1.0 - negative * 1.2
    if polarity == 0 and categories:
        polarity = 0.25
    polarity = max(-3.0, min(3.0, polarity))
    broad = any(phrase in text for phrase in BROAD_POSITIVE_PHRASES + BROAD_NEGATIVE_PHRASES)
    annotated = dict(item)
    annotated["categories"] = categories
    annotated["category_labels"] = [POLICY_CATEGORIES[key]["label"] for key in categories]
    annotated["polarity"] = round(polarity, 3)
    annotated["broad"] = broad
    annotated["policy_relevant"] = bool(categories) or broad
    return annotated


def contains_term(text: str, keyword: str) -> bool:
    """Match a keyword without treating 证券 as a hit inside 证监会."""
    if not keyword:
        return False
    start = 0
    while True:
        index = text.find(keyword, start)
        if index < 0:
            return False
        before = text[index - 1] if index else ""
        after = text[index + len(keyword) : index + len(keyword) + 2]
        if keyword == "证券" and before == "证":
            start = index + 1
            continue
        if keyword == "汇金" and after.startswith("科技"):
            start = index + len(keyword)
            continue
        return True


def select_relevant(items: list[dict[str, Any]], limit: int = 40) -> list[dict[str, Any]]:
    """Keep China policy headlines. Drop overseas tape and single-company enforcement."""
    chosen: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in items:
        item = annotate_macro_item(raw)
        title_key = re.sub(r"\s+", "", str(item.get("title", "")))
        if not title_key or title_key in seen:
            continue
        title = str(item.get("title") or "")
        if is_overseas_tape(title) or is_company_case(title):
            continue
        if "购金" in title and not any(phrase in title for phrase in ("降准", "逆回购", "MLF", "LPR", "回购增持再贷款")):
            continue
        if not item["policy_relevant"]:
            continue
        seen.add(title_key)
        chosen.append(item)
    chosen.sort(key=lambda row: str(row.get("time", "")), reverse=True)
    return chosen[:limit]


def recency_weight(item_time: object, asof: datetime) -> float:
    parsed = parse_cn_time(item_time)
    if parsed is None:
        return 0.6
    age_hours = (asof - parsed).total_seconds() / 3600
    if age_hours < -1:
        return 0.0
    if age_hours > 72:
        return 0.0
    if age_hours > 36:
        return 0.45
    if age_hours > 18:
        return 0.7
    return 1.0


def map_macro_news(
    items: list[dict[str, Any]],
    themes: list[Theme],
    *,
    asof: Optional[datetime] = None,
    headline_limit: int = 4,
) -> dict[str, Any]:
    moment = shanghai_now(asof)
    annotated = [annotate_macro_item(item) for item in items if item.get("title")]
    public_items = []
    seen: set[str] = set()
    for item in annotated:
        title_key = re.sub(r"\s+", "", str(item.get("title", "")))
        if title_key in seen:
            continue
        seen.add(title_key)
        if item.get("policy_relevant"):
            public_items.append(_public_item(item))
    public_items.sort(key=lambda row: str(row.get("time", "")), reverse=True)

    theme_views: dict[str, Any] = {}
    for theme in themes:
        keywords = policy_keywords_for(theme)
        raw = 0.0
        headlines: list[dict[str, Any]] = []
        for item in annotated:
            weight = _theme_weight(theme, item, keywords)
            decay = recency_weight(item.get("time"), moment)
            if weight <= 0 or decay <= 0:
                continue
            contribution = float(item.get("polarity") or 0) * weight * decay
            if contribution == 0 and not item.get("policy_relevant"):
                continue
            raw += contribution
            if len(headlines) < headline_limit:
                headlines.append(_public_item(item))
        theme_views[theme.id] = {
            "score": round(max(-8.0, min(8.0, raw)), 3),
            "available": bool(headlines),
            "headlines": headlines,
            "keywords": keywords,
        }

    broad_scores = [float(item.get("polarity") or 0) for item in annotated if item.get("broad") and recency_weight(item.get("time"), moment) > 0]
    return {
        "items": public_items[:12],
        "themes": theme_views,
        "market_wide_score": round(sum(broad_scores) / len(broad_scores), 3) if broad_scores else 0.0,
        "available": bool(public_items) or any(view["available"] for view in theme_views.values()),
        "asof": moment.isoformat(),
        "stale": any(str(item.get("stale") or "") in {"1", "true"} for item in items),
    }


def match_sector_for_theme(theme: Theme, boards: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    aliases = list(BOARD_ALIASES.get(theme.id, []))
    aliases.extend(policy_keywords_for(theme))
    for token in re.split(r"[\s/、,，]+", theme.name):
        if len(token.strip()) >= 2:
            aliases.append(token.strip())
    concepts: list[dict[str, Any]] = []
    industries: list[dict[str, Any]] = []
    for board in boards:
        name = str(board.get("name") or "")
        if not name:
            continue
        if not any(alias and (alias in name or name in alias) for alias in aliases):
            continue
        if board.get("board_type") == "concept":
            concepts.append(board)
        else:
            industries.append(board)
    pool = concepts or industries
    if not pool:
        return None
    pool.sort(key=lambda row: _num(row.get("pct")) or -999, reverse=True)
    best = pool[0]
    return {
        "name": best.get("name"),
        "pct": _num(best.get("pct")),
        "amount": _num(best.get("amount")),
        "board_type": best.get("board_type") or "industry",
        "source": best.get("source") or "",
    }


def _theme_weight(theme: Theme, item: dict[str, Any], keywords: list[str]) -> float:
    if is_overseas_tape(str(item.get("title") or "")) and not item.get("categories"):
        return 0.0
    text = f"{item.get('title', '')} {item.get('summary', '')}"
    weight = 1.0 if any(keyword and contains_term(text, keyword) for keyword in keywords) else 0.0
    for category in item.get("categories") or []:
        if category == "csrc" and not any(phrase in text for phrase in STRUCTURAL_CSRC):
            continue
        weight = max(weight, CATEGORY_THEME_BIAS.get(category, {}).get(theme.id, 0.0))
    if item.get("broad"):
        broad_weight = 0.9 if theme.id == "finance_brokerage_fintech" else 0.35
        weight = max(weight, broad_weight)
    return weight


def _public_item(item: dict[str, Any]) -> dict[str, Any]:
    summary = str(item.get("summary") or "")
    if len(summary) > 180:
        summary = summary[:180] + "…"
    return {
        "title": str(item.get("title") or ""),
        "summary": summary,
        "time": str(item.get("time") or ""),
        "source": str(item.get("source") or ""),
        "url": str(item.get("url") or ""),
        "origin": str(item.get("origin") or ""),
        "categories": list(item.get("categories") or []),
        "category_labels": list(item.get("category_labels") or []),
        "polarity": item.get("polarity"),
        "broad": bool(item.get("broad")),
        "stale": str(item.get("stale") or ""),
    }


def _num(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
