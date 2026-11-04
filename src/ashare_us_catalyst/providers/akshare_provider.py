from __future__ import annotations

from datetime import date, datetime, time as datetime_time, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any, Optional, Union
from urllib.parse import urlencode

import pandas as pd

from .common import CsvCache, first_column, normalize_history, to_number


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
}


class AkshareProvider:
    """Market data provider with fast direct endpoints and optional AkShare fallback.

    The daily report needs a bounded runtime. Direct Yahoo/Eastmoney calls are done
    through curl with hard timeouts. AkShare fallback is disabled by default because
    upstream retry loops can be slow when Eastmoney disconnects.
    """

    def __init__(
        self,
        cache_dir: Union[str, Path] = ".cache",
        use_cache: bool = True,
        timeout: float = 12,
        allow_akshare_fallback: Optional[bool] = None,
    ) -> None:
        self.cache = CsvCache(cache_dir, enabled=use_cache)
        self.timeout = timeout
        self.allow_akshare_fallback = (
            allow_akshare_fallback
            if allow_akshare_fallback is not None
            else os.environ.get("ASHARE_ALLOW_AKSHARE_FALLBACK") == "1"
        )
        self._ak = None
        self._sina_decoder = None

    @property
    def ak(self):
        if self._ak is None:
            import akshare as ak  # type: ignore

            self._ak = ak
        return self._ak

    def us_spot(self) -> pd.DataFrame:
        cached = self.cache.get("us_spot_em", max_age_hours=12)
        if cached is not None:
            return cached
        df = self.ak.stock_us_spot_em()
        self.cache.put("us_spot_em", df)
        return df

    def a_spot(self) -> pd.DataFrame:
        cached = self.cache.get("a_spot_em", max_age_hours=4)
        if cached is not None:
            return cached
        df = self.ak.stock_zh_a_spot_em()
        self.cache.put("a_spot_em", df)
        return df

    def resolve_us_symbol(self, ticker: str) -> str:
        if not self.allow_akshare_fallback:
            return ticker.upper()
        ticker = ticker.upper()
        try:
            df = self.us_spot()
        except Exception:
            return ticker
        code_col = first_column(df, ["代码", "symbol"])
        if code_col is None:
            return ticker
        for raw in df[code_col].astype(str):
            parts = raw.upper().split(".")
            if raw.upper() == ticker or parts[-1] == ticker:
                return raw
        return ticker

    def us_quote(self, ticker: str) -> dict[str, Any]:
        ticker = ticker.upper()
        hist = self.us_history(ticker, date.today() - timedelta(days=14), date.today(), resolve_em=False)
        if not hist.empty and hist["pct"].notna().any():
            latest = hist.dropna(subset=["pct"]).iloc[-1]
            return {
                "ticker": ticker,
                "name": ticker,
                "price": to_number(latest.get("close")),
                "pct": to_number(latest.get("pct")),
                "market_cap": None,
                "em_code": ticker,
            }

        if self.allow_akshare_fallback:
            try:
                df = self.us_spot()
                code_col = first_column(df, ["代码", "symbol"])
                if code_col:
                    for _, row in df.iterrows():
                        raw_code = str(row.get(code_col, "")).upper()
                        if raw_code == ticker or raw_code.split(".")[-1] == ticker:
                            return {
                                "ticker": ticker,
                                "name": _first_value(row, ["名称", "cname", "name"], ticker),
                                "price": to_number(_first_value(row, ["最新价", "price"], None)),
                                "pct": to_number(_first_value(row, ["涨跌幅", "chg"], None)),
                                "market_cap": to_number(_first_value(row, ["总市值", "mktcap"], None)),
                                "em_code": raw_code,
                            }
            except Exception:
                pass

        return {"ticker": ticker, "name": ticker, "price": None, "pct": None, "market_cap": None, "em_code": ticker}

    def us_history(self, ticker: str, start: date, end: date, resolve_em: bool = False) -> pd.DataFrame:
        ticker = ticker.upper()
        cache_name = f"us_hist_{ticker}_{start:%Y%m%d}_{end:%Y%m%d}"
        cached = self.cache.get(cache_name, max_age_hours=24)
        if cached is not None:
            return normalize_history(cached)

        last_error: Optional[Exception] = None
        try:
            out = self._sina_us_history(ticker, start, end)
            if not out.empty:
                self.cache.put(cache_name, out)
                return out
        except Exception as exc:
            last_error = exc

        try:
            out = self._yahoo_us_history(ticker, start, end)
            if not out.empty:
                self.cache.put(cache_name, out)
                return out
        except Exception as exc:
            last_error = exc

        if not self.allow_akshare_fallback:
            return pd.DataFrame(columns=["date", "close", "pct"])

        try:
            df = self.ak.stock_us_daily(symbol=ticker, adjust="qfq")
            out = normalize_history(df)
            out = out[(out["date"] >= pd.Timestamp(start)) & (out["date"] <= pd.Timestamp(end))]
            if not out.empty:
                self.cache.put(cache_name, out)
                return out
        except Exception as exc:
            last_error = exc

        symbols = [ticker]
        if resolve_em:
            resolved = self.resolve_us_symbol(ticker)
            if resolved != ticker:
                symbols.insert(0, resolved)

        for symbol in symbols:
            try:
                df = self.ak.stock_us_hist(
                    symbol=symbol,
                    period="daily",
                    start_date=start.strftime("%Y%m%d"),
                    end_date=end.strftime("%Y%m%d"),
                    adjust="qfq",
                )
                out = normalize_history(df)
                if not out.empty:
                    self.cache.put(cache_name, out)
                    return out
            except Exception as exc:
                last_error = exc

        if last_error:
            raise last_error
        return pd.DataFrame(columns=["date", "close", "pct"])

    def a_snapshot(self, code: str) -> dict[str, Any]:
        code = str(code).zfill(6)
        data: dict[str, Any] = {"code": code}
        direct_ok = False
        try:
            direct_data = self._eastmoney_a_snapshot(code)
            data.update(direct_data)
            direct_ok = bool(direct_data)
        except Exception:
            pass

        if not direct_ok:
            try:
                sina_data = self._sina_a_snapshot(code)
                data.update(sina_data)
                direct_ok = bool(sina_data)
            except Exception:
                pass

        if not direct_ok and self.allow_akshare_fallback:
            try:
                df = self.a_spot()
                code_col = first_column(df, ["代码"])
                if code_col:
                    match = df[df[code_col].astype(str).str.zfill(6) == code]
                    if not match.empty:
                        row = match.iloc[0]
                        data.update(
                            {
                                "name": _first_value(row, ["名称"], ""),
                                "price": to_number(_first_value(row, ["最新价"], None)),
                                "pct": to_number(_first_value(row, ["涨跌幅"], None)),
                                "market_cap": to_number(_first_value(row, ["总市值"], None)),
                                "float_market_cap": to_number(_first_value(row, ["流通市值"], None)),
                                "turnover_rate": to_number(_first_value(row, ["换手率"], None)),
                                "volume_ratio": to_number(_first_value(row, ["量比"], None)),
                                "pe": to_number(_first_value(row, ["市盈率-动态", "市盈率"], None)),
                            }
                        )
            except Exception:
                pass

            try:
                info = self.stock_info(code)
                data["industry"] = info.get("行业") or info.get("所处行业") or data.get("industry")
                data["market_cap"] = data.get("market_cap") or to_number(info.get("总市值"))
            except Exception:
                pass

        return data

    def stock_info(self, code: str) -> dict[str, Any]:
        code = str(code).zfill(6)
        cached = self.cache.get(f"a_info_{code}", max_age_hours=24 * 7)
        if cached is not None and {"item", "value"}.issubset(cached.columns):
            return {str(row["item"]): row["value"] for _, row in cached.iterrows()}
        df = self.ak.stock_individual_info_em(symbol=code, timeout=self.timeout)
        if df is not None and not df.empty:
            self.cache.put(f"a_info_{code}", df)
            item_col = first_column(df, ["item"])
            value_col = first_column(df, ["value"])
            if item_col and value_col:
                return {str(row[item_col]): row[value_col] for _, row in df.iterrows()}
        return {}

    def a_history(self, code: str, start: date, end: date) -> pd.DataFrame:
        code = str(code).zfill(6)
        cache_name = f"a_hist_{code}_{start:%Y%m%d}_{end:%Y%m%d}"
        cached = self.cache.get(cache_name, max_age_hours=24)
        cached_normalized = normalize_history(cached) if cached is not None else None
        if cached is not None:
            if _has_ohlc(cached_normalized):
                return cached_normalized
        nearest_cached = self._nearest_cached_a_history(code, start, end)
        try:
            out = self._eastmoney_a_history(code, start, end)
            if not out.empty:
                self.cache.put(cache_name, out)
                return out
        except Exception:
            pass

        if not self.allow_akshare_fallback:
            if nearest_cached is not None and not nearest_cached.empty:
                return nearest_cached
            return cached_normalized if cached_normalized is not None and not cached_normalized.empty else pd.DataFrame(columns=["date", "close", "pct"])

        df = self.ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            adjust="qfq",
            timeout=self.timeout,
        )
        out = normalize_history(df)
        self.cache.put(cache_name, out)
        return out

    def _nearest_cached_a_history(self, code: str, start: date, end: date) -> Optional[pd.DataFrame]:
        best: Optional[tuple[pd.Timestamp, float, pd.DataFrame]] = None
        for path in self.cache.cache_dir.glob(f"a_hist_{code}_*.csv"):
            try:
                out = normalize_history(pd.read_csv(path))
            except Exception:
                continue
            if out.empty:
                continue
            out = out[(out["date"] >= pd.Timestamp(start)) & (out["date"] <= pd.Timestamp(end))]
            if out.empty:
                continue
            latest_date = pd.Timestamp(out["date"].max())
            candidate = (latest_date, path.stat().st_mtime, out)
            if best is None or candidate[:2] > best[:2]:
                best = candidate
        return best[2] if best is not None else None

    def stock_news(self, code: str, name: str = "", limit: int = 5) -> list[dict[str, str]]:
        code = str(code).zfill(6)
        cache_name = f"news_{code}"
        cached = self.cache.get(cache_name, max_age_hours=8)
        if cached is None:
            try:
                df = self._eastmoney_news(code, limit=max(10, limit))
                self.cache.put(cache_name, df)
                cached = df
            except Exception:
                cached = None
        if cached is None and self.allow_akshare_fallback:
            df = self.ak.stock_news_em(symbol=code)
            self.cache.put(cache_name, df)
        else:
            df = cached
        if df is None or df.empty:
            return []
        title_col = first_column(df, ["新闻标题", "title"])
        time_col = first_column(df, ["发布时间", "date", "time"])
        source_col = first_column(df, ["文章来源", "source"])
        link_col = first_column(df, ["新闻链接", "url", "link"])
        news: list[dict[str, str]] = []
        for _, row in df.head(limit).iterrows():
            news.append(
                {
                    "title": str(row.get(title_col, "") if title_col else "").strip(),
                    "time": str(row.get(time_col, "") if time_col else "").strip(),
                    "source": str(row.get(source_col, "") if source_col else "").strip(),
                    "url": str(row.get(link_col, "") if link_col else "").strip(),
                }
            )
        return [item for item in news if item["title"]]

    def macro_news(self, limit: int = 40) -> list[dict[str, str]]:
        cache_name = "macro_news_v1"
        cached = self.cache.get(cache_name, max_age_hours=0.5)
        if cached is not None:
            return _records(cached)[:limit]
        items: list[dict[str, Any]] = []
        try:
            from .cn_public import fetch_macro_news

            items = fetch_macro_news(_curl_text, _curl_json, timeout=self.timeout, limit=max(40, limit))
        except Exception:
            items = []
        if items:
            self.cache.put(cache_name, pd.DataFrame(items))
            return items[:limit]
        stale = self.cache.get(cache_name)
        if stale is not None and not stale.empty:
            rows = _records(stale)[:limit]
            for row in rows:
                row["stale"] = "1"
            return rows
        return []

    def market_overview(self) -> dict[str, Any]:
        from ..clock import shanghai_now
        from .cn_public import fetch_market_overview

        cache_name = "market_overview_v1"
        cached = self.cache.get(cache_name, max_age_hours=0.2)
        if cached is not None:
            return _json_payload(cached)
        now = shanghai_now()
        try:
            overview = fetch_market_overview(
                _curl_text,
                _curl_json,
                timeout=self.timeout,
                today=now.date(),
                now=now,
            )
        except Exception as exc:
            overview = {"available": False, "warnings": [exc.__class__.__name__], "indices": [], "source": ""}
        overview["asof"] = now.isoformat()
        if overview.get("available"):
            self.cache.put(cache_name, pd.DataFrame([{"payload": json.dumps(overview, ensure_ascii=False)}]))
            return overview
        stale = self.cache.get(cache_name)
        if stale is not None and not stale.empty:
            restored = _json_payload(stale)
            restored["note"] = f"{restored.get('note') or ''} 使用过期缓存。".strip()
            restored["stale"] = True
            return restored
        return overview

    def sector_boards(self, limit: int = 20) -> list[dict[str, Any]]:
        from .cn_public import fetch_sector_boards

        cache_name = f"sector_boards_v1_{int(limit)}"
        cached = self.cache.get(cache_name, max_age_hours=0.2)
        if cached is not None:
            return _records(cached)
        try:
            rows, _warnings = fetch_sector_boards(_curl_json, timeout=self.timeout, limit=limit)
        except Exception:
            rows = []
        if rows:
            self.cache.put(cache_name, pd.DataFrame(rows))
            return rows
        stale = self.cache.get(cache_name)
        if stale is not None and not stale.empty:
            rows = _records(stale)
            for row in rows:
                row["stale"] = "1"
            return rows
        return []

    def quote_candidates(self, codes: list[str]) -> dict[str, dict[str, Any]]:
        from .cn_public import fetch_quote_batch

        normalized = [str(code).zfill(6) for code in codes]
        if not normalized:
            return {}
        digest = _quote_digest(normalized)
        cache_name = f"a_quotes_{digest}"
        cached = self.cache.get(cache_name, max_age_hours=0.1)
        if cached is not None:
            return {str(row.get("code")).zfill(6): row for row in _records(cached) if row.get("code")}
        merged: dict[str, dict[str, Any]] = {}
        for offset in range(0, len(normalized), 40):
            chunk = normalized[offset : offset + 40]
            try:
                merged.update(fetch_quote_batch(_curl_text, _curl_json, chunk, timeout=self.timeout))
            except Exception:
                continue
        if merged:
            self.cache.put(cache_name, pd.DataFrame(list(merged.values())))
        return merged

    def _yahoo_us_history(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        period1 = int(datetime.combine(start, datetime_time.min, tzinfo=timezone.utc).timestamp())
        period2 = int(datetime.combine(end + timedelta(days=1), datetime_time.min, tzinfo=timezone.utc).timestamp())
        payload = _curl_json(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
            params={
                "period1": period1,
                "period2": period2,
                "interval": "1d",
                "events": "history",
                "includeAdjustedClose": "true",
            },
            timeout=self.timeout,
        )
        result = payload["chart"]["result"][0]
        timestamps = result.get("timestamp") or []
        quote = (result.get("indicators", {}).get("quote") or [{}])[0]
        adjclose_items = result.get("indicators", {}).get("adjclose") or []
        adjclose = adjclose_items[0].get("adjclose") if adjclose_items else None
        close_values = adjclose or quote.get("close") or []
        open_values = quote.get("open") or []
        high_values = quote.get("high") or []
        low_values = quote.get("low") or []
        volume_values = quote.get("volume") or []
        rows = []
        for index, (ts, close) in enumerate(zip(timestamps, close_values)):
            if close is None:
                continue
            rows.append(
                {
                    "date": datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None).date(),
                    "open": _list_value(open_values, index),
                    "high": _list_value(high_values, index),
                    "low": _list_value(low_values, index),
                    "close": float(close),
                    "volume": _list_value(volume_values, index),
                }
            )
        out = pd.DataFrame(rows)
        if out.empty:
            return pd.DataFrame(columns=["date", "close", "pct"])
        out["date"] = pd.to_datetime(out["date"]).dt.normalize()
        out = out.sort_values("date").drop_duplicates("date", keep="last")
        out["pct"] = out["close"].pct_change() * 100
        columns = ["date", "close", "pct", "open", "high", "low", "volume"]
        return out[[col for col in columns if col in out.columns]].dropna(subset=["pct"])

    def _sina_us_history(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        full_cache_name = f"us_hist_sina_full_{ticker}"
        cached = self.cache.get(full_cache_name, max_age_hours=24)
        if cached is not None:
            out = normalize_history(cached)
            return out[(out["date"] >= pd.Timestamp(start)) & (out["date"] <= pd.Timestamp(end))]
        text = _curl_text(f"https://finance.sina.com.cn/staticdata/us/{ticker}", params={}, timeout=self.timeout)
        if "=" not in text:
            return pd.DataFrame(columns=["date", "close", "pct"])
        encoded = text.split("=", 1)[1].split(";", 1)[0].replace('"', "")
        records = self._decode_sina_payload(encoded)
        out = normalize_history(pd.DataFrame(records))
        if not out.empty:
            self.cache.put(full_cache_name, out)
        out = out[(out["date"] >= pd.Timestamp(start)) & (out["date"] <= pd.Timestamp(end))]
        return out

    def _decode_sina_payload(self, encoded: str) -> list[dict[str, Any]]:
        if self._sina_decoder is None:
            from akshare.stock.cons import zh_js_decode  # type: ignore
            from py_mini_racer import MiniRacer  # type: ignore

            js_code = MiniRacer()
            js_code.eval(zh_js_decode)
            self._sina_decoder = js_code
        return self._sina_decoder.call("d", encoded)

    def _eastmoney_a_snapshot(self, code: str) -> dict[str, Any]:
        payload = _curl_json(
            "https://push2.eastmoney.com/api/qt/stock/get",
            params={"secid": _eastmoney_secid(code), "fields": "f57,f58,f43,f170,f116,f117,f168,f10,f9,f23,f86"},
            timeout=self.timeout,
        )
        data = (payload or {}).get("data") or {}
        if not data:
            return {}
        quote_time = _eastmoney_quote_datetime(data.get("f86"))
        return _sanitize_a_snapshot_quote({
            "code": str(data.get("f57") or code).zfill(6),
            "name": data.get("f58") or "",
            "price": _scaled(data.get("f43"), 100),
            "pct": _scaled(data.get("f170"), 100),
            "market_cap": to_number(data.get("f116")),
            "float_market_cap": to_number(data.get("f117")),
            "turnover_rate": _scaled(data.get("f168"), 100),
            "volume_ratio": _scaled(data.get("f10"), 100),
            "pe": _scaled(data.get("f9"), 100),
            "pb": _scaled(data.get("f23"), 100),
            "pct_source": "eastmoney_snapshot",
            "pct_date": quote_time.date().isoformat() if quote_time else "",
            "snapshot_time": quote_time.strftime("%H:%M:%S") if quote_time else "",
        })

    def _sina_a_snapshot(self, code: str) -> dict[str, Any]:
        market_code = f"{'sh' if str(code).startswith(('5', '6', '9')) else 'sz'}{str(code).zfill(6)}"
        text = _curl_text(
            "https://hq.sinajs.cn/list=" + market_code,
            params={},
            timeout=self.timeout,
            referer="https://finance.sina.com.cn",
            encoding="gb18030",
        )
        match = re.search(r'="(.*)"', text, flags=re.S)
        if not match:
            return {}
        parts = match.group(1).split(",")
        if len(parts) < 32 or not parts[0]:
            return {}
        prev_close = to_number(parts[2])
        price = to_number(parts[3])
        pct = ((price / prev_close) - 1) * 100 if price is not None and prev_close else None
        return _sanitize_a_snapshot_quote({
            "code": str(code).zfill(6),
            "name": parts[0],
            "open": to_number(parts[1]),
            "prev_close": prev_close,
            "price": price,
            "pct": pct,
            "high": to_number(parts[4]),
            "low": to_number(parts[5]),
            "volume": to_number(parts[8]),
            "amount": to_number(parts[9]),
            "pct_source": "sina_snapshot",
            "pct_date": parts[30] if len(parts) > 30 and parts[30] else date.today().isoformat(),
            "snapshot_time": parts[31] if len(parts) > 31 else "",
        })

    def _eastmoney_a_history(self, code: str, start: date, end: date) -> pd.DataFrame:
        payload = _curl_json(
            "https://push2his.eastmoney.com/api/qt/stock/kline/get",
            params={
                "secid": _eastmoney_secid(code),
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                "klt": "101",
                "fqt": "1",
                "beg": start.strftime("%Y%m%d"),
                "end": end.strftime("%Y%m%d"),
            },
            timeout=self.timeout,
        )
        data = (payload or {}).get("data") or {}
        rows = []
        for line in data.get("klines") or []:
            parts = str(line).split(",")
            if len(parts) >= 9:
                rows.append(
                    {
                        "date": parts[0],
                        "open": parts[1],
                        "close": parts[2],
                        "high": parts[3],
                        "low": parts[4],
                        "volume": parts[5],
                        "amount": parts[6],
                        "pct": parts[8],
                        "turnover_rate": parts[10] if len(parts) > 10 else None,
                    }
                )
        return normalize_history(pd.DataFrame(rows))

    def _eastmoney_news(self, code: str, limit: int = 10) -> pd.DataFrame:
        inner_param = {
            "uid": "",
            "keyword": code,
            "type": ["cmsArticleWebOld"],
            "client": "web",
            "clientType": "web",
            "clientVersion": "curr",
            "param": {
                "cmsArticleWebOld": {
                    "searchScope": "default",
                    "sort": "default",
                    "pageIndex": 1,
                    "pageSize": limit,
                    "preTag": "<em>",
                    "postTag": "</em>",
                }
            },
        }
        callback = "jQuery_ashare_us_catalyst"
        text = _curl_text(
            "https://search-api-web.eastmoney.com/search/jsonp",
            params={"cb": callback, "param": json.dumps(inner_param, ensure_ascii=False), "_": str(int(time.time() * 1000))},
            timeout=self.timeout,
            referer=f"https://so.eastmoney.com/news/s?keyword={code}",
        )
        match = re.match(r"^.*?\((.*)\);?$", text, flags=re.S)
        if not match:
            return pd.DataFrame()
        payload = json.loads(match.group(1))
        rows = []
        for item in (payload.get("result", {}).get("cmsArticleWebOld", []) or [])[:limit]:
            article_code = item.get("code", "")
            rows.append(
                {
                    "关键词": code,
                    "新闻标题": _clean_html(item.get("title", "")),
                    "新闻内容": _clean_html(item.get("content", "")),
                    "发布时间": item.get("date", ""),
                    "文章来源": item.get("mediaName", ""),
                    "新闻链接": f"http://finance.eastmoney.com/a/{article_code}.html" if article_code else "",
                }
            )
        return pd.DataFrame(rows)


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    rows = []
    for raw in df.to_dict(orient="records"):
        item = {}
        for key, value in raw.items():
            if pd.isna(value):
                item[key] = None
            else:
                item[key] = value
        rows.append(item)
    return rows


def _json_payload(df: pd.DataFrame) -> dict[str, Any]:
    if df is None or df.empty or "payload" not in df.columns:
        return {"available": False}
    try:
        payload = json.loads(df.iloc[0]["payload"])
    except (TypeError, json.JSONDecodeError):
        return {"available": False}
    return payload if isinstance(payload, dict) else {"available": False}


def _quote_digest(codes: list[str]) -> str:
    import hashlib

    return hashlib.sha1(",".join(sorted(codes)).encode("utf-8")).hexdigest()[:12]


def _first_value(row: pd.Series, names: list[str], default: Any) -> Any:
    for name in names:
        if name in row and pd.notna(row[name]):
            return row[name]
    lowered = {str(key).lower(): key for key in row.index}
    for name in names:
        key = lowered.get(name.lower())
        if key is not None and pd.notna(row[key]):
            return row[key]
    return default


def _sanitize_a_snapshot_quote(data: dict[str, Any]) -> dict[str, Any]:
    """Treat zero-price pre-open quotes as unavailable, not as -100% moves."""
    price = to_number(data.get("price"))
    pct = to_number(data.get("pct"))
    if (price is not None and price <= 0) or (pct is not None and pct <= -99.9):
        data["price"] = None
        data["pct"] = None
        data["pct_source"] = "not_open"
    return data


def _eastmoney_quote_datetime(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if re.fullmatch(r"20\d{12}", text):
        return datetime.strptime(text, "%Y%m%d%H%M%S")
    if re.fullmatch(r"20\d{6}", text):
        return datetime.strptime(text, "%Y%m%d")
    num = to_number(value)
    if num is None:
        return None
    try:
        if num > 10_000_000_000:
            num = num / 1000
        if num > 1_000_000_000:
            return datetime.fromtimestamp(num)
    except (OSError, OverflowError, ValueError):
        return None
    return None


def _eastmoney_secid(code: str) -> str:
    market = "1" if str(code).startswith(("5", "6", "9")) else "0"
    return f"{market}.{str(code).zfill(6)}"


def _scaled(value: Any, scale: float) -> Optional[float]:
    num = to_number(value)
    if num is None:
        return None
    return num / scale


def _list_value(values: list[Any], index: int) -> Optional[float]:
    if index >= len(values):
        return None
    return to_number(values[index])


def _has_ohlc(df: Optional[pd.DataFrame]) -> bool:
    return df is not None and not df.empty and {"open", "high", "low", "close"}.issubset(df.columns)


def _clean_html(value: Any) -> str:
    text = re.sub(r"<.*?>", "", str(value or ""))
    return text.replace("\u3000", "").replace("\r\n", " ").strip()


def _curl_json(url: str, params: dict[str, Any], timeout: float) -> dict[str, Any]:
    return json.loads(_curl_text(url, params=params, timeout=timeout))


def _curl_text(
    url: str,
    params: dict[str, Any],
    timeout: float,
    referer: Optional[str] = None,
    encoding: str = "utf-8",
) -> str:
    query = urlencode(params) if params else ""
    full_url = f"{url}?{query}" if query else url
    timeout_seconds = max(3, int(timeout))
    cmd = [
        "curl",
        "-L",
        "--silent",
        "--show-error",
        "--max-time",
        str(timeout_seconds),
        "-A",
        DEFAULT_HEADERS["User-Agent"],
    ]
    if referer:
        cmd.extend(["-e", referer])
    cmd.append(full_url)
    proc = subprocess.run(
        cmd,
        capture_output=True,
        timeout=timeout_seconds + 2,
        check=False,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(stderr or f"curl failed with code {proc.returncode}")
    if not proc.stdout:
        raise RuntimeError("curl returned empty response")
    return proc.stdout.decode(encoding, errors="replace")
