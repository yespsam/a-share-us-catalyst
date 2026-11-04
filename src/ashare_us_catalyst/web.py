from __future__ import annotations

from datetime import date, datetime
from http import HTTPStatus
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import json
from pathlib import Path
import sys
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from .asia_markets import load_asia_markets_config, screen_asia_markets
from .clock import shanghai_now
from .config import load_config
from .backtest import run_backtest
from .intraday import build_intraday_report, render_intraday_markdown, write_intraday_outputs
from .multibagger import discover_multibaggers, load_multibagger_config
from .providers import AkshareProvider, SampleProvider
from .report import render_markdown, write_outputs
from .scoring import rank_report
from .us_quality import load_us_quality_config, screen_us_quality


ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = ROOT / "web"


class CatalystHandler(SimpleHTTPRequestHandler):
    server_version = "CatalystWeb/0.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/report":
            self._handle_report(parsed.query)
            return
        if parsed.path == "/api/intraday":
            self._handle_intraday(parsed.query)
            return
        if parsed.path == "/api/us-quality":
            self._handle_us_quality(parsed.query)
            return
        if parsed.path == "/api/asia-markets":
            self._handle_asia_markets(parsed.query)
            return
        if parsed.path == "/api/multibagger":
            self._handle_multibagger(parsed.query)
            return
        if parsed.path == "/api/backtest":
            self._handle_backtest(parsed.query)
            return
        if parsed.path == "/api/history":
            self._handle_history()
            return
        if parsed.path == "/api/health":
            self._send_json({"ok": True, "root": str(ROOT)})
            return
        if parsed.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write("[web] " + format % args + "\n")

    def _handle_report(self, query: str) -> None:
        try:
            params = parse_qs(query)
            sample = _bool_param(params, "sample", False)
            report_date = _date_param(params, "date") or shanghai_now().date()
            top = _int_param(params, "top", 5)
            max_themes = _int_param(params, "maxThemes", 4)
            lookback = _int_param(params, "lookback", 420)
            skip_news = _bool_param(params, "skipNews", False)
            skip_macro = _bool_param(params, "skipMacro", False)
            legacy_weights = _bool_param(params, "legacyWeights", False)
            provider = SampleProvider() if sample else AkshareProvider(ROOT / ".cache-web", use_cache=True)
            config = load_config(ROOT / "config/themes.json")
            result = rank_report(
                config.themes,
                provider,
                report_date=report_date,
                top_n=top,
                lookback_days=lookback,
                skip_news=skip_news,
                max_themes=max_themes,
                skip_macro=skip_macro,
                legacy_weights=legacy_weights,
            )
            markdown = render_markdown(result, config.report.get("risk_note", "本报告不构成投资建议。"))
            md_path, json_path = write_outputs(result, markdown, ROOT / "reports-web")
            self._send_json(
                {
                    "ok": True,
                    "result": result,
                    "markdown": markdown,
                    "markdownPath": str(md_path),
                    "jsonPath": str(json_path),
                }
            )
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_intraday(self, query: str) -> None:
        try:
            params = parse_qs(query)
            sample = _bool_param(params, "sample", False)
            report_date = _date_param(params, "date") or shanghai_now().date()
            top_sectors = _int_param(params, "topSectors", 8)
            provider = SampleProvider() if sample else AkshareProvider(ROOT / ".cache-web", use_cache=True)
            config = load_config(ROOT / "config/themes.json")
            result = build_intraday_report(
                config.themes,
                provider,
                report_date=report_date,
                top_sectors=top_sectors,
            )
            markdown = render_intraday_markdown(result)
            md_path, json_path = write_intraday_outputs(result, markdown, ROOT / "reports-web")
            self._send_json(
                {
                    "ok": True,
                    "result": result,
                    "markdown": markdown,
                    "markdownPath": str(md_path),
                    "jsonPath": str(json_path),
                }
            )
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_us_quality(self, query: str) -> None:
        try:
            params = parse_qs(query)
            sample = _bool_param(params, "sample", False)
            report_date = _date_param(params, "date") or date.today()
            top = _int_param(params, "top", 20)
            lookback = _int_param(params, "lookback", 260)
            provider = SampleProvider() if sample else AkshareProvider(ROOT / ".cache-web", use_cache=True)
            config = load_us_quality_config(ROOT / "config/us_quality.json")
            result = screen_us_quality(
                config["universe"],
                provider,
                report_date=report_date,
                top_n=top,
                lookback_days=lookback,
            )
            self._send_json({"ok": True, "result": result, "riskNote": config["report"].get("risk_note", "")})
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_asia_markets(self, query: str) -> None:
        try:
            params = parse_qs(query)
            sample = _bool_param(params, "sample", False)
            report_date = _date_param(params, "date") or date.today()
            top = _int_param(params, "top", 24)
            lookback = _int_param(params, "lookback", 260)
            provider = SampleProvider() if sample else AkshareProvider(ROOT / ".cache-web", use_cache=True)
            config = load_asia_markets_config(ROOT / "config/asia_markets.json")
            result = screen_asia_markets(
                config["universe"],
                provider,
                report_date=report_date,
                top_n=top,
                lookback_days=lookback,
            )
            self._send_json({"ok": True, "result": result, "riskNote": config["report"].get("risk_note", "")})
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_multibagger(self, query: str) -> None:
        try:
            params = parse_qs(query)
            sample = _bool_param(params, "sample", False)
            report_date = _date_param(params, "date") or date.today()
            top = _int_param(params, "top", 24)
            lookback = _int_param(params, "lookback", 360)
            skip_news = _bool_param(params, "skipNews", False)
            provider = SampleProvider() if sample else AkshareProvider(ROOT / ".cache-web", use_cache=True)
            app_config = load_config(ROOT / "config/themes.json")
            multibagger_config = load_multibagger_config(ROOT / "config/multibagger.json")
            result = discover_multibaggers(
                app_config.themes,
                multibagger_config["us_universe"],
                provider,
                report_date=report_date,
                top_n=top,
                lookback_days=lookback,
                skip_news=skip_news,
            )
            self._send_json({"ok": True, "result": result, "riskNote": multibagger_config["report"].get("risk_note", "")})
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_backtest(self, query: str) -> None:
        try:
            params = parse_qs(query)
            sample = _bool_param(params, "sample", False)
            report_date = _date_param(params, "date") or date.today()
            window = _int_param(params, "window", 182)
            lookback = _int_param(params, "lookback", 260)
            provider = SampleProvider() if sample else AkshareProvider(ROOT / ".cache-web", use_cache=True)
            app_config = load_config(ROOT / "config/themes.json")
            us_config = load_us_quality_config(ROOT / "config/us_quality.json")
            result = run_backtest(
                app_config.themes,
                us_config["universe"],
                provider,
                report_date=report_date,
                window_days=window,
                lookback_days=lookback,
                top_n=5,
            )
            self._send_json({"ok": True, "result": result})
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_history(self) -> None:
        reports_dir = ROOT / "reports-web"
        items = []
        if reports_dir.exists():
            paths = list(reports_dir.glob("*-morning.md")) + list(reports_dir.glob("*-intraday-*.md"))
            paths = [path for path in paths if "latest" not in path.name]
            for path in sorted(paths, key=lambda item: item.stat().st_mtime, reverse=True)[:20]:
                items.append({"name": path.name, "path": str(path), "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat()})
        self._send_json({"ok": True, "items": items})

    def _send_json(self, data: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _bool_param(params: dict[str, list[str]], key: str, default: bool) -> bool:
    value = params.get(key, [str(default).lower()])[0].lower()
    return value in {"1", "true", "yes", "on"}


def _int_param(params: dict[str, list[str]], key: str, default: int) -> int:
    try:
        return int(params.get(key, [str(default)])[0])
    except ValueError:
        return default


def _date_param(params: dict[str, list[str]], key: str) -> Optional[date]:
    raw = params.get(key, [""])[0]
    if not raw:
        return None
    return datetime.strptime(raw, "%Y-%m-%d").date()


def main(argv: Optional[list[str]] = None) -> int:
    port = 8765
    if argv and len(argv) >= 1:
        port = int(argv[0])
    server = ThreadingHTTPServer(("127.0.0.1", port), CatalystHandler)
    print(f"Web dashboard: http://127.0.0.1:{port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
