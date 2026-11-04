from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ..clock import shanghai_now

import numpy as np
import pandas as pd


class SampleProvider:
    """Deterministic offline data for testing the report shape."""

    def __init__(self) -> None:
        self.rng = np.random.default_rng(7)

    def us_quote(self, ticker: str) -> dict[str, Any]:
        pct_map = {
            "NVDA": 4.2,
            "AMD": 2.1,
            "AVGO": 3.4,
            "MU": 1.8,
            "TSLA": 2.6,
            "PDD": 1.7,
            "LLY": 1.2,
            "FCX": 2.4,
            "HOOD": 3.1,
            "LMT": -0.2,
        }
        pct = pct_map.get(ticker.upper(), self._stable_pct(ticker))
        return {"ticker": ticker.upper(), "name": ticker.upper(), "price": 100.0, "pct": pct, "market_cap": None}

    def us_history(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        return self._series(start, end, drift=self._stable_pct(ticker) / 250, scale=1.8, seed=ticker)

    def a_snapshot(self, code: str) -> dict[str, Any]:
        base = int(code[-3:]) if code[-3:].isdigit() else 100
        return {
            "code": code,
            "name": "",
            "price": 10 + base / 80,
            "pct": (base % 9) - 3,
            "market_cap": (base + 80) * 100_000_000,
            "float_market_cap": (base + 60) * 70_000_000,
            "turnover_rate": 1 + (base % 7),
            "volume_ratio": 0.8 + (base % 5) * 0.2,
            "pe": 20 + (base % 40),
        }

    def a_history(self, code: str, start: date, end: date) -> pd.DataFrame:
        drift = ((int(code[-2:]) if code[-2:].isdigit() else 20) - 35) / 3000
        return self._series(start, end, drift=drift, scale=2.3, seed=code)

    def stock_news(self, code: str, name: str = "", limit: int = 5) -> list[dict[str, str]]:
        titles = [
            f"{name or code} 获得 AI 数据中心订单，机构称产业链需求延续",
            f"{name or code} 发布业绩预告，收入保持增长",
            f"{name or code} 与头部客户签署战略合作协议",
            f"{name or code} 近期接受机构调研，关注产能释放节奏",
            f"{name or code} 公告回购计划并提示市场波动风险",
        ]
        today = date.today()
        return [
            {
                "title": title,
                "time": str(today - timedelta(days=i)),
                "source": "样例源",
                "url": "",
            }
            for i, title in enumerate(titles[:limit])
        ]

    def macro_news(self, limit: int = 40) -> list[dict[str, str]]:
        moment = shanghai_now()
        stamp = moment.strftime("%Y-%m-%d")
        items = [
            {
                "title": "央行开展逆回购并下调股票回购增持再贷款利率",
                "summary": "公开市场保持流动性合理充裕，稳市工具加力。样例快讯，不是实时新闻。",
                "time": f"{stamp} 08:30:00",
                "source": "样例源",
                "url": "",
                "origin": "sample",
            },
            {
                "title": "工信部：继续推进人工智能算力基础设施和芯片产业",
                "summary": "产业政策提及算力、芯片和国产替代。样例快讯，不是实时新闻。",
                "time": f"{stamp} 08:10:00",
                "source": "样例源",
                "url": "",
                "origin": "sample",
            },
            {
                "title": "证监会就减持新规征求意见，强调从严监管",
                "summary": "资本市场规则预期转严。样例快讯，不是实时新闻。",
                "time": f"{stamp} 07:50:00",
                "source": "样例源",
                "url": "",
                "origin": "sample",
            },
            {
                "title": "黄金与有色价格走强，资源板块情绪升温",
                "summary": "黄金、有色链条受关注。样例快讯，不是实时新闻。",
                "time": f"{stamp} 07:40:00",
                "source": "样例源",
                "url": "",
                "origin": "sample",
            },
        ]
        return items[:limit]

    def market_overview(self) -> dict[str, Any]:
        moment = shanghai_now()
        return {
            "available": True,
            "source": "sample",
            "asof": moment.isoformat(),
            "trade_date": moment.date().isoformat(),
            "limit_up_count": 42,
            "limit_down_count": 6,
            "amount": 835_000_000_000,
            "advance": None,
            "decline": None,
            "indices": [
                {"code": "000001", "name": "上证指数", "pct": 0.62, "amount": 420_000_000_000, "price": 3280.0, "source": "sample"},
                {"code": "399001", "name": "深证成指", "pct": 0.84, "amount": 415_000_000_000, "price": 10880.0, "source": "sample"},
            ],
            "note": "离线样例，不是实时行情。",
            "warnings": [],
        }

    def sector_boards(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = [
            {"code": "BK0447", "name": "半导体", "pct": 3.4, "amount": 48_000_000_000, "turnover_rate": 4.2, "board_type": "industry", "source": "sample", "rank_side": "leader", "up_count": 70, "member_count": 90, "leader_name": "样例芯片", "leader_pct": 8.1},
            {"code": "BK0732", "name": "机器人", "pct": 2.6, "amount": 18_000_000_000, "turnover_rate": 5.1, "board_type": "concept", "source": "sample", "rank_side": "leader", "leader_name": "样例自动化", "leader_pct": 6.4},
            {"code": "BK0473", "name": "证券", "pct": 1.8, "amount": 32_000_000_000, "turnover_rate": 2.4, "board_type": "industry", "source": "sample", "rank_side": "leader", "up_count": 40, "member_count": 50, "leader_name": "样例券商", "leader_pct": 4.2},
            {"code": "BK0478", "name": "有色金属", "pct": 1.2, "amount": 21_000_000_000, "turnover_rate": 2.1, "board_type": "industry", "source": "sample", "rank_side": "leader", "up_count": 30, "member_count": 45},
            {"code": "BK0438", "name": "食品饮料", "pct": -1.6, "amount": 12_000_000_000, "turnover_rate": 0.8, "board_type": "industry", "source": "sample", "rank_side": "laggard", "up_count": 8, "member_count": 40},
            {"code": "BK0428", "name": "电力", "pct": -0.7, "amount": 9_000_000_000, "turnover_rate": 0.6, "board_type": "industry", "source": "sample", "rank_side": "laggard", "up_count": 12, "member_count": 36},
        ]
        return rows[:limit]

    def quote_candidates(self, codes: list[str]) -> dict[str, dict[str, Any]]:
        overlay = {
            "300308": {"pct": 12.4, "volume_ratio": 2.8, "turnover_rate": 6.2, "amount": 3_200_000_000, "price": 120.5},
            "600030": {"pct": -6.1, "volume_ratio": 2.2, "turnover_rate": 4.1, "amount": 1_500_000_000, "price": 28.4},
            "300059": {"pct": 5.4, "volume_ratio": 1.4, "turnover_rate": 3.3, "amount": 2_100_000_000, "price": 22.0},
        }
        quotes = {}
        moment = shanghai_now()
        for code in codes:
            padded = str(code).zfill(6)
            snapshot = dict(self.a_snapshot(padded))
            snapshot.update(overlay.get(padded, {}))
            snapshot["code"] = padded
            snapshot["pct_source"] = "sample"
            snapshot["pct_date"] = moment.date().isoformat()
            snapshot["snapshot_time"] = moment.strftime("%H:%M:%S")
            quotes[padded] = snapshot
        return quotes

    def _series(self, start: date, end: date, drift: float, scale: float, seed: str) -> pd.DataFrame:
        dates = pd.bdate_range(start=start, end=end)
        local = np.random.default_rng(abs(hash(seed)) % (2**32))
        pct = local.normal(loc=drift * 100, scale=scale, size=len(dates))
        close = 100 * np.cumprod(1 + pct / 100)
        open_ = close / (1 + pct / 100)
        spread = np.abs(local.normal(loc=0.8, scale=0.35, size=len(dates)))
        high = np.maximum(open_, close) * (1 + spread / 100)
        low = np.minimum(open_, close) * (1 - spread / 100)
        volume = local.integers(800_000, 8_000_000, size=len(dates))
        return pd.DataFrame({"date": dates.normalize(), "open": open_, "high": high, "low": low, "close": close, "pct": pct, "volume": volume})

    def _stable_pct(self, key: str) -> float:
        return ((abs(hash(key)) % 700) / 100) - 2.5
