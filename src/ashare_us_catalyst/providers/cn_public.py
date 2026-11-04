"""Lightweight public China market reads.

Eastmoney is tried first, matching the rest of this project. Tencent and Sina
cover the hosts that currently fail or time out. Failures stay in the returned
warnings; callers keep cache and empty-state fallbacks. Nothing here invents a
quote when a payload is missing.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
import re
import time
from typing import Any, Callable, Optional

from ..macro_news import select_relevant
from .common import to_number


CurlJson = Callable[..., dict[str, Any]]
CurlText = Callable[..., str]


def fetch_macro_news(curl_text: CurlText, curl_json: CurlJson, *, timeout: float, limit: int = 40) -> list[dict[str, Any]]:
    started = time.time()
    collected: list[dict[str, Any]] = []
    try:
        payload = curl_json(
            "https://np-listapi.eastmoney.com/comm/web/getFastNewsList",
            params={
                "client": "web",
                "biz": "web_724",
                "fastColumn": "102",
                "sortEnd": "",
                "pageSize": "80",
                "req_trace": str(int(time.time() * 1000)),
            },
            timeout=min(timeout, 8),
        )
        collected.extend(parse_fast_news(payload))
    except Exception:
        pass

    relevant = select_relevant(collected, limit=limit)
    policy_count = sum(1 for item in relevant if item.get("policy_relevant"))
    if policy_count < 6:
        for keyword in ("央行", "证监会", "汇金", "产业政策"):
            if time.time() - started > 18:
                break
            try:
                text = curl_text(
                    "https://search-api-web.eastmoney.com/search/jsonp",
                    params={
                        "cb": "jQuery_catdesk_macro",
                        "param": json.dumps(_search_param(keyword, page_size=8), ensure_ascii=False),
                        "_": str(int(time.time() * 1000)),
                    },
                    timeout=min(timeout, 6),
                    referer=f"https://so.eastmoney.com/news/s?keyword={keyword}",
                )
                collected.extend(parse_search_news(unwrap_jsonp(text), keyword))
            except Exception:
                continue
    return select_relevant(collected, limit=limit)


def fetch_market_overview(
    curl_text: CurlText,
    curl_json: CurlJson,
    *,
    timeout: float,
    today: date,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    indices: list[dict[str, Any]] = []
    try:
        payload = curl_json(
            "https://push2.eastmoney.com/api/qt/ulist.np/get",
            params={"fltt": "2", "secids": "1.000001,0.399001", "fields": "f2,f3,f6,f12,f14"},
            timeout=min(timeout, 4),
        )
        indices = parse_eastmoney_indices(payload)
    except Exception as exc:
        warnings.append(f"东财指数不可用：{exc.__class__.__name__}")
    if not indices:
        try:
            text = curl_text(
                "https://hq.sinajs.cn/list=s_sh000001,s_sz399001",
                params={},
                timeout=min(timeout, 6),
                referer="https://finance.sina.com.cn",
                encoding="gb18030",
            )
            indices = parse_sina_indices(text)
        except Exception as exc:
            warnings.append(f"新浪指数不可用：{exc.__class__.__name__}")

    moment = now or datetime.now()
    limit_up = None
    limit_down = None
    trade_date = ""
    pool_note = ""
    for session_date in _session_dates(today, 5):
        try:
            payload = curl_json(
                "https://push2ex.eastmoney.com/getTopicZTPool",
                params=_limit_pool_params(session_date),
                timeout=min(timeout, 8),
            )
        except Exception as exc:
            warnings.append(f"涨停池 {session_date.isoformat()} 不可用：{exc.__class__.__name__}")
            continue
        count = parse_limit_pool_count(payload)
        if count is None:
            continue
        if count == 0 and _before_open(session_date, moment):
            pool_note = "今日涨停池尚未形成，改用最近一个有数据的交易日。"
            continue
        limit_up = count
        trade_date = session_date.isoformat()
        limit_down = _limit_down_count(curl_json, session_date, timeout, warnings)
        break

    amount = None
    amounts = [row["amount"] for row in indices if row.get("amount") is not None]
    if amounts:
        amount = float(sum(amounts))
    available = bool(indices) or limit_up is not None
    return {
        "available": available,
        "source": _overview_source(indices, limit_up),
        "asof": "",
        "trade_date": trade_date,
        "limit_up_count": limit_up,
        "limit_down_count": limit_down,
        "amount": amount,
        "advance": None,
        "decline": None,
        "indices": indices,
        "note": pool_note,
        "warnings": warnings,
    }


def fetch_sector_boards(curl_json: CurlJson, *, timeout: float, limit: int = 20) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    rows: list[dict[str, Any]] = []
    try:
        industry = curl_json(
            "https://push2.eastmoney.com/api/qt/clist/get",
            params=_eastmoney_board_params("m:90+t:2+f:!50", limit),
            timeout=min(timeout, 4),
        )
        concept = curl_json(
            "https://push2.eastmoney.com/api/qt/clist/get",
            params=_eastmoney_board_params("m:90+t:3+f:!50", limit),
            timeout=min(timeout, 4),
        )
        laggards = curl_json(
            "https://push2.eastmoney.com/api/qt/clist/get",
            params=_eastmoney_board_params("m:90+t:2+f:!50", min(5, limit), ascending=True),
            timeout=min(timeout, 4),
        )
        rows.extend(parse_eastmoney_boards(industry, "industry", rank_side="leader"))
        rows.extend(parse_eastmoney_boards(concept, "concept", rank_side="leader"))
        rows.extend(parse_eastmoney_boards(laggards, "industry", rank_side="laggard"))
    except Exception as exc:
        warnings.append(f"东财板块不可用：{exc.__class__.__name__}")
    if rows:
        return _dedupe_boards(rows), warnings
    try:
        industry = curl_json(
            "https://proxy.finance.qq.com/cgi/cgi-bin/rank/pt/getRank",
            params={"board_type": "hy", "sort_type": "priceRatio", "direct": "down", "offset": "0", "count": str(limit)},
            timeout=min(timeout, 8),
        )
        laggards = curl_json(
            "https://proxy.finance.qq.com/cgi/cgi-bin/rank/pt/getRank",
            params={"board_type": "hy", "sort_type": "priceRatio", "direct": "up", "offset": "0", "count": str(min(5, limit))},
            timeout=min(timeout, 8),
        )
        concept = curl_json(
            "https://proxy.finance.qq.com/cgi/cgi-bin/rank/pt/getRank",
            params={"board_type": "gn", "sort_type": "priceRatio", "direct": "down", "offset": "0", "count": str(max(8, limit // 2))},
            timeout=min(timeout, 8),
        )
        rows.extend(parse_tencent_boards(industry, "industry", rank_side="leader"))
        rows.extend(parse_tencent_boards(laggards, "industry", rank_side="laggard"))
        rows.extend(parse_tencent_boards(concept, "concept", rank_side="leader"))
    except Exception as exc:
        warnings.append(f"腾讯板块不可用：{exc.__class__.__name__}")
    return _dedupe_boards(rows), warnings


def fetch_quote_batch(
    curl_text: CurlText,
    curl_json: CurlJson,
    codes: list[str],
    *,
    timeout: float,
) -> dict[str, dict[str, Any]]:
    normalized = [str(code).zfill(6) for code in codes]
    if not normalized:
        return {}
    try:
        payload = curl_json(
            "https://push2.eastmoney.com/api/qt/ulist.np/get",
            params={
                "fltt": "2",
                "secids": ",".join(_eastmoney_secid(code) for code in normalized),
                "fields": "f2,f3,f6,f8,f9,f10,f12,f14,f20",
            },
            timeout=min(timeout, 4),
        )
        parsed = parse_eastmoney_quotes(payload)
        if parsed:
            return parsed
    except Exception:
        pass
    try:
        symbols = ",".join(_tencent_symbol(code) for code in normalized)
        text = curl_text(
            f"https://qt.gtimg.cn/q={symbols}",
            params={},
            timeout=min(timeout, 8),
            encoding="gbk",
        )
        parsed = parse_tencent_quotes(text)
        if parsed:
            return parsed
    except Exception:
        pass
    try:
        symbols = ",".join(_sina_symbol(code) for code in normalized)
        text = curl_text(
            "https://hq.sinajs.cn/list=" + symbols,
            params={},
            timeout=min(timeout, 8),
            referer="https://finance.sina.com.cn",
            encoding="gb18030",
        )
        return parse_sina_quotes(text)
    except Exception:
        return {}


def parse_fast_news(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = (payload or {}).get("data") or {}
    rows = []
    for item in data.get("fastNewsList") or []:
        title = clean_text(item.get("title"))
        summary = clean_text(item.get("summary"))
        if not title:
            title = summary[:80]
        if not title:
            continue
        code = str(item.get("code") or "")
        rows.append(
            {
                "title": title,
                "summary": summary,
                "time": str(item.get("showTime") or ""),
                "source": "东方财富7x24",
                "url": f"https://finance.eastmoney.com/a/{code}.html" if code else "",
                "origin": "eastmoney_fast",
            }
        )
    return rows


def parse_search_news(payload: dict[str, Any], keyword: str) -> list[dict[str, Any]]:
    articles = ((payload or {}).get("result") or {}).get("cmsArticleWebOld") or []
    rows = []
    for item in articles:
        title = clean_text(item.get("title"))
        if not title:
            continue
        code = str(item.get("code") or "")
        rows.append(
            {
                "title": title,
                "summary": clean_text(item.get("content")),
                "time": str(item.get("date") or ""),
                "source": str(item.get("mediaName") or "东方财富搜索"),
                "url": f"https://finance.eastmoney.com/a/{code}.html" if code else "",
                "origin": f"eastmoney_search:{keyword}",
            }
        )
    return rows


def parse_limit_pool_count(payload: dict[str, Any]) -> Optional[int]:
    data = (payload or {}).get("data")
    if not isinstance(data, dict) or "tc" not in data or data.get("tc") is None:
        return None
    try:
        return int(data.get("tc"))
    except (TypeError, ValueError):
        return None


def parse_sina_indices(text: str) -> list[dict[str, Any]]:
    rows = []
    for match in re.finditer(r'hq_str_s_([a-z]{2}\d+)="(.*)"', text or ""):
        parts = match.group(2).split(",")
        if len(parts) < 6 or not parts[0]:
            continue
        amount_wan = to_number(parts[5])
        rows.append(
            {
                "code": match.group(1)[-6:],
                "name": parts[0],
                "price": to_number(parts[1]),
                "pct": to_number(parts[3]),
                "amount": None if amount_wan is None else amount_wan * 10_000,
                "source": "sina_index",
            }
        )
    return rows


def parse_eastmoney_indices(payload: dict[str, Any]) -> list[dict[str, Any]]:
    diff = _diff_rows(payload)
    rows = []
    for item in diff:
        name = item.get("f14") or ""
        if not name:
            continue
        rows.append(
            {
                "code": str(item.get("f12") or "").zfill(6),
                "name": name,
                "price": to_number(item.get("f2")),
                "pct": to_number(item.get("f3")),
                "amount": to_number(item.get("f6")),
                "source": "eastmoney_index",
            }
        )
    return rows


def parse_eastmoney_boards(payload: dict[str, Any], board_type: str, rank_side: str = "") -> list[dict[str, Any]]:
    rows = []
    for item in _diff_rows(payload):
        name = item.get("f14") or ""
        if not name:
            continue
        rows.append(
            {
                "code": str(item.get("f12") or ""),
                "name": name,
                "pct": to_number(item.get("f3")),
                "amount": to_number(item.get("f6")),
                "turnover_rate": to_number(item.get("f8")),
                "board_type": board_type,
                "source": "eastmoney_board",
                "rank_side": rank_side,
            }
        )
    return rows


def parse_tencent_boards(payload: dict[str, Any], board_type: str, rank_side: str = "") -> list[dict[str, Any]]:
    rank_list = ((payload or {}).get("data") or {}).get("rank_list") or []
    rows = []
    for item in rank_list:
        name = item.get("name") or ""
        if not name:
            continue
        up_count, member_count = _split_count(item.get("zgb"))
        turnover = to_number(item.get("turnover"))
        leader = item.get("lzg") or {}
        rows.append(
            {
                "code": str(item.get("code") or ""),
                "name": name,
                "pct": to_number(item.get("zdf")),
                "amount": None if turnover is None else turnover * 10_000,
                "turnover_rate": to_number(item.get("hsl")),
                "volume_ratio": to_number(item.get("lb")),
                "up_count": up_count,
                "member_count": member_count,
                "leader_name": leader.get("name") or "",
                "leader_pct": to_number(leader.get("zdf")),
                "board_type": board_type,
                "source": "tencent_board",
                "rank_side": rank_side,
            }
        )
    return rows


def parse_tencent_quotes(text: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for match in re.finditer(r'v_[a-z]{2}\d+="([^"]*)"', text or ""):
        item = parse_tencent_quote_body(match.group(1))
        if item.get("code"):
            out[item["code"]] = item
    return out


def parse_tencent_quote_body(body: str) -> dict[str, Any]:
    parts = (body or "").split("~")

    def at(index: int) -> str:
        return parts[index] if index < len(parts) else ""

    code = str(at(2)).zfill(6) if at(2) else ""
    price = to_number(at(3))
    pct = to_number(at(32))
    if price is not None and price <= 0:
        price = None
        pct = None
    amount_wan = to_number(at(37))
    market_cap_yi = to_number(at(45))
    stamp = at(30)
    pct_date = ""
    snapshot_time = ""
    if len(stamp) >= 8 and stamp[:8].isdigit():
        pct_date = f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]}"
        if len(stamp) >= 14 and stamp[:14].isdigit():
            snapshot_time = f"{stamp[8:10]}:{stamp[10:12]}:{stamp[12:14]}"
    return {
        "code": code,
        "name": at(1),
        "price": price,
        "pct": pct,
        "amount": None if amount_wan is None else amount_wan * 10_000,
        "turnover_rate": to_number(at(38)),
        "volume_ratio": to_number(at(49)),
        "pe": to_number(at(39)),
        "market_cap": None if market_cap_yi is None else market_cap_yi * 100_000_000,
        "pct_source": "tencent_quote",
        "pct_date": pct_date,
        "snapshot_time": snapshot_time,
    }


def parse_sina_quotes(text: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for match in re.finditer(r'hq_str_([a-z]{2}\d+)="(.*)"', text or "", flags=re.S):
        parts = match.group(2).split(",")
        if len(parts) < 32 or not parts[0]:
            continue
        code = match.group(1)[-6:]
        prev_close = to_number(parts[2])
        price = to_number(parts[3])
        pct = ((price / prev_close) - 1) * 100 if price and prev_close else None
        if price is not None and price <= 0:
            price = None
            pct = None
        out[code] = {
            "code": code,
            "name": parts[0],
            "price": price,
            "pct": pct,
            "amount": to_number(parts[9]),
            "turnover_rate": None,
            "volume_ratio": None,
            "pct_source": "sina_batch",
            "pct_date": parts[30] if len(parts) > 30 else "",
            "snapshot_time": parts[31] if len(parts) > 31 else "",
        }
    return out


def parse_eastmoney_quotes(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in _diff_rows(payload):
        code = str(item.get("f12") or "").zfill(6)
        if not code.strip("0") and code != "000000":
            if not item.get("f14"):
                continue
        price = to_number(item.get("f2"))
        pct = to_number(item.get("f3"))
        if price is not None and price <= 0:
            price = None
            pct = None
        if not code:
            continue
        out[code] = {
            "code": code,
            "name": item.get("f14") or "",
            "price": price,
            "pct": pct,
            "amount": to_number(item.get("f6")),
            "turnover_rate": to_number(item.get("f8")),
            "volume_ratio": to_number(item.get("f10")),
            "pe": to_number(item.get("f9")),
            "market_cap": to_number(item.get("f20")),
            "pct_source": "eastmoney_ulist",
            "pct_date": "",
            "snapshot_time": "",
        }
    return out


def unwrap_jsonp(text: str) -> dict[str, Any]:
    match = re.search(r"\((.*)\)\s*;?\s*$", text or "", flags=re.S)
    if not match:
        return {}
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def clean_text(value: Any) -> str:
    text = re.sub(r"<.*?>", "", str(value or ""))
    return re.sub(r"\s+", " ", text).replace("\u3000", "").strip()


def _search_param(keyword: str, page_size: int) -> dict[str, Any]:
    return {
        "uid": "",
        "keyword": keyword,
        "type": ["cmsArticleWebOld"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {
            "cmsArticleWebOld": {
                "searchScope": "default",
                "sort": "default",
                "pageIndex": 1,
                "pageSize": page_size,
                "preTag": "",
                "postTag": "",
            }
        },
    }


def _limit_pool_params(session_date: date) -> dict[str, str]:
    return {
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "dpt": "wz.ztzt",
        "Pageindex": "0",
        "pagesize": "1",
        "sort": "fbt:asc",
        "date": session_date.strftime("%Y%m%d"),
    }


def _eastmoney_board_params(fs: str, limit: int, ascending: bool = False) -> dict[str, str]:
    return {
        "pn": "1",
        "pz": str(limit),
        "po": "0" if ascending else "1",
        "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2",
        "invt": "2",
        "fid": "f3",
        "fs": fs,
        "fields": "f12,f14,f2,f3,f6,f8,f104,f105",
    }


def _limit_down_count(curl_json: CurlJson, session_date: date, timeout: float, warnings: list[str]) -> Optional[int]:
    try:
        payload = curl_json(
            "https://push2ex.eastmoney.com/getTopicDTPool",
            params=_limit_pool_params(session_date),
            timeout=min(timeout, 8),
        )
    except Exception as exc:
        warnings.append(f"跌停池不可用：{exc.__class__.__name__}")
        return None
    return parse_limit_pool_count(payload)


def _session_dates(today: date, count: int) -> list[date]:
    dates: list[date] = []
    cursor = today
    while len(dates) < count:
        if cursor.weekday() < 5:
            dates.append(cursor)
        cursor -= timedelta(days=1)
    return dates


def _before_open(session_date: date, now: datetime) -> bool:
    if now.date() != session_date:
        return False
    return now.hour * 60 + now.minute < 9 * 60 + 35


def _overview_source(indices: list[dict[str, Any]], limit_up: Optional[int]) -> str:
    parts = []
    if indices:
        parts.append(str(indices[0].get("source") or "index"))
    if limit_up is not None:
        parts.append("eastmoney_limit_pool")
    return "+".join(parts)


def _dedupe_boards(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    out = []
    for row in rows:
        key = (str(row.get("board_type") or ""), str(row.get("name") or ""), str(row.get("rank_side") or ""))
        if not row.get("name") or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _diff_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = (payload or {}).get("data") or {}
    diff = data.get("diff") or []
    if isinstance(diff, dict):
        return [row for row in diff.values() if isinstance(row, dict)]
    return [row for row in diff if isinstance(row, dict)]


def _split_count(value: Any) -> tuple[Optional[int], Optional[int]]:
    text = str(value or "")
    if "/" not in text:
        return None, None
    left, right = text.split("/", 1)
    return _int_or_none(left), _int_or_none(right)


def _int_or_none(value: Any) -> Optional[int]:
    number = to_number(value)
    if number is None:
        return None
    return int(number)


def _eastmoney_secid(code: str) -> str:
    market = "1" if str(code).startswith(("5", "6", "9")) else "0"
    return f"{market}.{str(code).zfill(6)}"


def _tencent_symbol(code: str) -> str:
    padded = str(code).zfill(6)
    if padded.startswith(("5", "6", "9")):
        return "sh" + padded
    if padded.startswith(("8", "4")) or padded.startswith("92"):
        return "bj" + padded
    return "sz" + padded


def _sina_symbol(code: str) -> str:
    padded = str(code).zfill(6)
    if padded.startswith(("5", "6", "9")):
        return "sh" + padded
    if padded.startswith(("8", "4")) or padded.startswith("92"):
        return "bj" + padded
    return "sz" + padded
