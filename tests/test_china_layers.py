from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from ashare_us_catalyst.cli import main
from ashare_us_catalyst.clock import shanghai_now
from ashare_us_catalyst.config import Candidate, Theme, UsTicker, load_config
from ashare_us_catalyst.intraday import anomaly_flags, build_intraday_report, limit_pct_threshold, session_name
from ashare_us_catalyst.macro_news import annotate_macro_item, map_macro_news, recency_weight
from ashare_us_catalyst.providers.cn_public import (
    parse_eastmoney_boards,
    parse_fast_news,
    parse_limit_pool_count,
    parse_sina_indices,
    parse_tencent_boards,
    parse_tencent_quote_body,
)
from ashare_us_catalyst.providers.sample_provider import SampleProvider
from ashare_us_catalyst.scoring import (
    CHINA_LOCAL_WEIGHTS,
    LEGACY_WEIGHTS,
    china_catalyst_score,
    rank_report,
    score_candidate,
)


def _theme(theme_id: str = "ai_compute_semis", name: str = "AI算力") -> Theme:
    return Theme(
        id=theme_id,
        name=name,
        logic="test",
        us_tickers=[UsTicker(ticker="NVDA", name="NVIDIA", weight=1)],
        candidates=[Candidate(code="300308", name="中际旭创", industry="光模块", rationale="test")],
    )


class MacroNewsTests(unittest.TestCase):
    def test_policy_headline_is_tagged_and_mapped(self) -> None:
        easing = annotate_macro_item({"title": "央行下调股票回购增持再贷款利率", "summary": "保持流动性合理充裕"})
        tightening = annotate_macro_item({"title": "证监会就减持新规征求意见，强调从严监管", "summary": ""})
        self.assertIn("pboc", easing["categories"])
        self.assertIn("stabilizer", easing["categories"])
        self.assertGreater(easing["polarity"], 0)
        self.assertLess(tightening["polarity"], 0)

        moment = datetime(2026, 11, 4, 10, 0, tzinfo=timezone(timedelta(hours=8)))
        mapped = map_macro_news(
            [
                {"title": easing["title"], "summary": easing["summary"], "time": "2026-11-04 08:30:00", "source": "fixture"},
                {"title": "工信部提及人工智能算力与芯片", "summary": "产业政策", "time": "2026-11-04 08:00:00", "source": "fixture"},
                {"title": tightening["title"], "summary": "", "time": "2026-11-04 07:50:00", "source": "fixture"},
            ],
            [_theme(), _theme("finance_brokerage_fintech", "券商")],
            asof=moment,
        )
        self.assertGreater(mapped["themes"]["ai_compute_semis"]["score"], 0)
        self.assertTrue(mapped["themes"]["ai_compute_semis"]["available"])
        self.assertTrue(mapped["items"])
        self.assertLess(mapped["themes"]["finance_brokerage_fintech"]["score"], mapped["themes"]["ai_compute_semis"]["score"])
        overseas = map_macro_news(
            [{"title": "费城半导体指数跌1.3%", "summary": "美股盘中", "time": "2026-11-04 22:30:00", "source": "fixture"}],
            [_theme()],
            asof=moment,
        )
        self.assertFalse(overseas["themes"]["ai_compute_semis"]["available"])
        foreign = map_macro_news(
            [{"title": "波兰央行将主要利率维持在3.75%", "summary": "", "time": "2026-11-04 21:00:00", "source": "fixture"}],
            [_theme("finance_brokerage_fintech", "券商")],
            asof=moment,
        )
        self.assertFalse(foreign["themes"]["finance_brokerage_fintech"]["available"])
        sweden = map_macro_news(
            [{"title": "瑞典央行上调政策利率至2.00%", "summary": "", "time": "2026-11-04 16:00:00", "source": "fixture"}],
            [_theme("finance_brokerage_fintech", "券商")],
            asof=moment,
        )
        self.assertFalse(sweden["themes"]["finance_brokerage_fintech"]["available"])
        case = map_macro_news(
            [{"title": "天山股份被证监会立案", "summary": "", "time": "2026-11-04 21:00:00", "source": "fixture"}],
            [_theme("finance_brokerage_fintech", "券商")],
            asof=moment,
        )
        self.assertFalse(case["themes"]["finance_brokerage_fintech"]["available"])
        company = map_macro_news(
            [{"title": "汇金科技：2026年第一次临时股东会决议公告", "summary": "", "time": "2026-11-02 21:00:00", "source": "fixture"}],
            [_theme("finance_brokerage_fintech", "券商")],
            asof=moment,
        )
        self.assertFalse(company["themes"]["finance_brokerage_fintech"]["available"])

    def test_future_and_stale_headlines_do_not_score(self) -> None:
        moment = datetime(2026, 11, 4, 9, 0, tzinfo=timezone(timedelta(hours=8)))
        self.assertEqual(recency_weight("2026-11-05 09:00:00", moment), 0.0)
        self.assertEqual(recency_weight("2026-10-01 09:00:00", moment), 0.0)
        self.assertEqual(recency_weight("2026-11-04 08:00:00", moment), 1.0)


class ScoringWeightTests(unittest.TestCase):
    def test_weight_profiles_keep_the_same_positive_sum(self) -> None:
        self.assertAlmostEqual(sum(LEGACY_WEIGHTS.values()), 0.96)
        self.assertAlmostEqual(sum(CHINA_LOCAL_WEIGHTS.values()), 0.96)
        self.assertEqual(CHINA_LOCAL_WEIGHTS["china_catalyst"], 0.22)

    def test_legacy_signal_weight_is_unchanged(self) -> None:
        signal = {"score": 80}
        stats = {"hit_rate": None, "avg_after_signal": None, "corr": None, "beta": None}
        snapshot = {"pct": 1.0, "turnover_rate": 2.0, "market_cap": 200_000_000_000}
        candidate = Candidate(code="300308", name="中际旭创", industry="光模块", rationale="test")
        _total, factors = score_candidate(signal, stats, snapshot, 1.0, candidate)
        self.assertEqual(factors["signal"], round(80 * 0.34, 2))
        self.assertEqual(factors["china_catalyst"], 0.0)

        _total, china_factors = score_candidate(
            signal,
            stats,
            snapshot,
            1.0,
            candidate,
            weight_profile="china_local_v1",
            china_catalyst=80,
        )
        self.assertEqual(china_factors["signal"], round(80 * 0.24, 2))
        self.assertEqual(china_factors["china_catalyst"], round(80 * 0.22, 2))

    def test_missing_china_inputs_stay_neutral(self) -> None:
        neutral = china_catalyst_score(policy_score=None, policy_available=False, market={}, sector=None, snapshot={})
        self.assertEqual(neutral["score"], 50)
        self.assertFalse(neutral["available"])
        hot = china_catalyst_score(
            policy_score=4,
            policy_available=True,
            market={"available": True, "limit_up_count": 80, "limit_down_count": 2, "trade_date": "2026-11-04"},
            sector={"name": "半导体", "pct": 3},
            snapshot={"volume_ratio": 2.4, "turnover_rate": 4, "amount": 2_000_000_000},
        )
        cold = china_catalyst_score(
            policy_score=-4,
            policy_available=True,
            market={"available": True, "limit_up_count": 8, "limit_down_count": 40, "trade_date": "2026-11-04"},
            sector={"name": "半导体", "pct": -3},
            snapshot={"volume_ratio": 0.4, "turnover_rate": 20},
        )
        self.assertGreater(hot["score"], neutral["score"])
        self.assertLess(cold["score"], neutral["score"])


class ReportIntegrationTests(unittest.TestCase):
    def test_sample_morning_uses_china_profile_for_today(self) -> None:
        today = shanghai_now().date()
        result = rank_report(
            load_config(Path("config/themes.json")).themes[:1],
            SampleProvider(),
            report_date=today,
            top_n=1,
            lookback_days=30,
            max_themes=1,
        )
        self.assertEqual(result["scoring"]["profile"], "china_local_v1")
        self.assertIn("不是买入指令", result["scoring"]["note"])
        self.assertTrue(result["macro"]["items"])
        factor = result["themes"][0]["top"][0]["factors"]["china_catalyst"]
        self.assertGreater(factor, 0)
        self.assertIn("china_catalyst", result["themes"][0]["top"][0]["analyst"]["dimensions"])

    def test_historical_date_does_not_reuse_live_tape(self) -> None:
        result = rank_report(
            [_theme()],
            SampleProvider(),
            report_date=date(2026, 1, 5),
            top_n=1,
            lookback_days=20,
        )
        self.assertEqual(result["scoring"]["profile"], "legacy")
        self.assertTrue(result["scoring"]["fallback"])

    def test_provider_failure_falls_back(self) -> None:
        class DownProvider(SampleProvider):
            def macro_news(self, limit: int = 40):
                raise RuntimeError("news down")

            def market_overview(self):
                raise RuntimeError("tape down")

            def sector_boards(self, limit: int = 20):
                raise RuntimeError("boards down")

        result = rank_report([_theme()], DownProvider(), report_date=shanghai_now().date(), top_n=1, lookback_days=20)
        self.assertEqual(result["scoring"]["profile"], "legacy")
        self.assertTrue(result["scoring"]["fallback"])


class IntradayTests(unittest.TestCase):
    def test_limit_thresholds_and_flags(self) -> None:
        self.assertEqual(limit_pct_threshold("600030", "中信证券"), 9.8)
        self.assertEqual(limit_pct_threshold("300308", "中际旭创"), 19.5)
        self.assertEqual(limit_pct_threshold("600000", "ST示例"), 4.9)
        self.assertEqual(
            anomaly_flags({"code": "600030", "name": "中信证券", "pct": 10.0, "volume_ratio": 3}),
            ["limit_up", "large_up", "volume_spike"],
        )
        self.assertEqual(anomaly_flags({"code": "600030", "name": "中信证券", "pct": None}), [])

    def test_session_names(self) -> None:
        zone = timezone(timedelta(hours=8))
        self.assertEqual(session_name(datetime(2026, 11, 4, 10, 15, tzinfo=zone)), "morning")
        self.assertEqual(session_name(datetime(2026, 11, 4, 14, 0, tzinfo=zone)), "afternoon")
        self.assertEqual(session_name(datetime(2026, 11, 4, 9, 10, tzinfo=zone)), "preopen")
        self.assertEqual(session_name(datetime(2026, 11, 7, 10, 0, tzinfo=zone)), "closed")

    def test_sample_intraday_report_has_sections_without_inventing_failures(self) -> None:
        moment = datetime(2026, 11, 4, 10, 15, tzinfo=timezone(timedelta(hours=8)))
        result = build_intraday_report(load_config("config/themes.json").themes, SampleProvider(), now=moment, report_date=date(2026, 11, 4))
        self.assertEqual(result["kind"], "intraday")
        self.assertEqual(result["market"]["limit_up_count"], 42)
        self.assertEqual(result["market"]["source"], "sample")
        self.assertIn("不是买卖指令", result["risk_note"])
        self.assertTrue(result["sectors"]["leaders"])
        self.assertTrue(result["sectors"]["laggards"])
        flags = {flag for row in result["anomalies"]["rows"] for flag in row["flags"]}
        self.assertIn("large_up", flags)
        self.assertIn("volume_spike", flags)
        self.assertTrue(result["policy_flashes"]["items"])
        self.assertNotIn(None, [row.get("pct") for row in result["anomalies"]["rows"]])

    def test_broken_market_still_returns_anomalies(self) -> None:
        class Partial(SampleProvider):
            def market_overview(self):
                raise RuntimeError("down")

            def sector_boards(self, limit: int = 20):
                return []

        moment = datetime(2026, 11, 4, 10, 15, tzinfo=timezone(timedelta(hours=8)))
        result = build_intraday_report([_theme()], Partial(), now=moment, report_date=date(2026, 11, 4))
        self.assertFalse(result["market"]["available"])
        self.assertEqual(result["sectors"]["status"], "unavailable")
        self.assertTrue(result["anomalies"]["rows"])
        self.assertIn(result["status"], {"partial", "ok"})

    def test_cli_sample_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            morning = main(
                [
                    "--sample-data",
                    "--date",
                    shanghai_now().date().isoformat(),
                    "--top",
                    "1",
                    "--max-themes",
                    "1",
                    "--lookback-days",
                    "20",
                    "--output",
                    str(root),
                    "--cache",
                    str(root / "cache"),
                ]
            )
            intraday = main(["intraday", "--sample-data", "--output", str(root), "--cache", str(root / "cache")])
            self.assertEqual(morning, 0)
            self.assertEqual(intraday, 0)
            morning_json = next(root.glob("*-morning.json"))
            payload = json.loads(morning_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["scoring"]["profile"], "china_local_v1")
            self.assertTrue(root.joinpath("intraday-latest.json").exists())


class ParserTests(unittest.TestCase):
    def test_public_payload_parsers_do_not_fill_missing_counts(self) -> None:
        news = parse_fast_news(
            {"data": {"fastNewsList": [{"title": "央行开展逆回购", "summary": "流动性", "showTime": "2026-11-04 08:00:00", "code": "1"}]}}
        )
        self.assertEqual(news[0]["origin"], "eastmoney_fast")
        self.assertIsNone(parse_limit_pool_count({"data": None}))
        self.assertEqual(parse_limit_pool_count({"data": {"tc": 0}}), 0)
        indices = parse_sina_indices('var hq_str_s_sh000001="上证指数,3200,10,0.30,100,200000";')
        self.assertEqual(indices[0]["amount"], 2_000_000_000)
        boards = parse_tencent_boards(
            {"data": {"rank_list": [{"name": "电子", "zdf": "1.5", "turnover": "10000", "zgb": "10/20", "hsl": "1.2", "lb": "1.1", "lzg": {"name": "样例", "zdf": "3"}}]}},
            "industry",
            rank_side="leader",
        )
        self.assertEqual(boards[0]["amount"], 100_000_000)
        self.assertEqual(boards[0]["up_count"], 10)
        east = parse_eastmoney_boards({"data": {"diff": [{"f12": "BK1", "f14": "半导体", "f3": 2.5, "f6": 1000}]}}, "industry")
        self.assertEqual(east[0]["pct"], 2.5)
        parts = [""] * 50
        parts[1] = "中际旭创"
        parts[2] = "300308"
        parts[3] = "100"
        parts[30] = "20261104101500"
        parts[32] = "11.07"
        parts[37] = "50000"
        parts[38] = "3.2"
        parts[49] = "1.8"
        quote = parse_tencent_quote_body("~".join(parts))
        self.assertEqual(quote["code"], "300308")
        self.assertAlmostEqual(quote["pct"], 11.07)
        self.assertEqual(quote["amount"], 500_000_000)
        self.assertEqual(quote["pct_source"], "tencent_quote")


if __name__ == "__main__":
    unittest.main()
