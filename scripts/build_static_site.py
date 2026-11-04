from __future__ import annotations

from datetime import date, datetime
import json
import os
from pathlib import Path
import shutil

from ashare_us_catalyst.asia_markets import load_asia_markets_config, screen_asia_markets
from ashare_us_catalyst.backtest import run_backtest
from ashare_us_catalyst.config import load_config
from ashare_us_catalyst.intraday import build_intraday_report, render_intraday_markdown
from ashare_us_catalyst.multibagger import discover_multibaggers, load_multibagger_config
from ashare_us_catalyst.providers import AkshareProvider, SampleProvider
from ashare_us_catalyst.report import render_markdown
from ashare_us_catalyst.scoring import rank_report
from ashare_us_catalyst.us_quality import load_us_quality_config, screen_us_quality


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def main() -> int:
    if DIST.exists():
        shutil.rmtree(DIST)
    shutil.copytree(ROOT / "web", DIST, ignore=shutil.ignore_patterns("assets/dashboard-concept.png"))
    data_dir = DIST / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    sample_data = os.environ.get("CATDESK_SAMPLE_DATA", "").lower() in {"1", "true", "yes"}
    provider = SampleProvider() if sample_data else AkshareProvider(ROOT / ".cache-static", use_cache=True)
    report_date = report_date_from_env()

    app_config = load_config(ROOT / "config/themes.json")
    report = rank_report(
        app_config.themes,
        provider,
        report_date=report_date,
        top_n=5,
        lookback_days=420,
        skip_news=False,
        max_themes=6,
    )
    markdown = render_markdown(report, app_config.report.get("risk_note", "本报告不构成投资建议。"))
    intraday = build_intraday_report(app_config.themes, provider, report_date=report_date, top_sectors=8)
    intraday_markdown = render_intraday_markdown(intraday)

    us_config = load_us_quality_config(ROOT / "config/us_quality.json")
    us_quality = screen_us_quality(
        us_config["universe"],
        provider,
        report_date=report_date,
        top_n=20,
        lookback_days=260,
    )
    asia_config = load_asia_markets_config(ROOT / "config/asia_markets.json")
    asia_markets = screen_asia_markets(
        asia_config["universe"],
        provider,
        report_date=report_date,
        top_n=int(asia_config["report"].get("default_top_n", 24)),
        lookback_days=int(asia_config["report"].get("default_lookback_days", 260)),
    )
    multibagger_config = load_multibagger_config(ROOT / "config/multibagger.json")
    multibagger = discover_multibaggers(
        app_config.themes,
        multibagger_config["us_universe"],
        provider,
        report_date=report_date,
        top_n=int(multibagger_config["report"].get("default_top_n", 24)),
        lookback_days=int(multibagger_config["report"].get("default_lookback_days", 360)),
    )
    backtest = run_backtest(
        app_config.themes,
        us_config["universe"],
        provider,
        report_date=report_date,
        window_days=182,
        lookback_days=260,
        top_n=5,
    )

    write_json(data_dir / "report.json", {"ok": True, "result": report, "markdown": markdown, "markdownPath": "static://data/report.md"})
    write_json(data_dir / "intraday.json", {"ok": True, "result": intraday, "markdown": intraday_markdown, "markdownPath": "static://data/intraday.md"})
    write_json(data_dir / "us-quality.json", {"ok": True, "result": us_quality, "riskNote": us_config["report"].get("risk_note", "")})
    write_json(data_dir / "asia-markets.json", {"ok": True, "result": asia_markets, "riskNote": asia_config["report"].get("risk_note", "")})
    write_json(data_dir / "multibagger.json", {"ok": True, "result": multibagger, "riskNote": multibagger_config["report"].get("risk_note", "")})
    write_json(data_dir / "backtest.json", {"ok": True, "result": backtest})
    write_json(data_dir / "history.json", {"ok": True, "items": [{"name": f"{report_date}-morning.md", "path": "static://data/report.md"}]})
    (data_dir / "report.md").write_text(markdown, encoding="utf-8")
    (data_dir / "intraday.md").write_text(intraday_markdown, encoding="utf-8")
    (DIST / "_headers").write_text(
        "/data/*.json\n  Cache-Control: public, max-age=300\n/*.html\n  Cache-Control: public, max-age=60\n",
        encoding="utf-8",
    )
    if os.environ.get("CATDESK_INLINE_CSS", "").lower() in {"1", "true", "yes"}:
        inline_css(DIST / "index.html", DIST / "styles.css")
    print(f"Built static site: {DIST}")
    return 0


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def report_date_from_env() -> date:
    value = os.environ.get("CATDESK_REPORT_DATE", "").strip()
    if not value:
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def inline_css(index_path: Path, css_path: Path) -> None:
    html = index_path.read_text(encoding="utf-8")
    css = css_path.read_text(encoding="utf-8")
    link = '    <link rel="stylesheet" href="styles.css?v=20261104-cn1" />'
    style = f"    <style>\n{css}\n    </style>\n{link}"
    index_path.write_text(html.replace(link, style), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
