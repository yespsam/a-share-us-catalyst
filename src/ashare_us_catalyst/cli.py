from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
import sys
from typing import Optional

from .clock import shanghai_now
from .config import load_config
from .intraday import build_intraday_report, render_intraday_markdown, write_intraday_outputs
from .notifier import load_env, send_telegram
from .providers import AkshareProvider, SampleProvider
from .report import render_markdown, write_outputs
from .scoring import rank_report


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成美股映射 A 股早报")
    parser.add_argument("--config", default="config/themes.json", help="板块和候选池配置")
    parser.add_argument("--output", default="reports", help="报告输出目录")
    parser.add_argument("--cache", default=".cache", help="行情缓存目录")
    parser.add_argument("--top", type=int, default=None, help="每个板块输出股票数量")
    parser.add_argument("--lookback-days", type=int, default=None, help="历史回看天数")
    parser.add_argument("--max-themes", type=int, default=None, help="只输出信号最强的 N 个板块")
    parser.add_argument("--date", default=None, help="报告日期，格式 YYYY-MM-DD，默认今天")
    parser.add_argument("--sample-data", action="store_true", help="使用离线样例数据")
    parser.add_argument("--skip-news", action="store_true", help="不抓取个股新闻")
    parser.add_argument("--skip-macro", action="store_true", help="不抓取宏观/政策新闻，盘口与板块仍会尝试")
    parser.add_argument("--legacy-weights", action="store_true", help="使用旧评分权重，不把中国本地催化计入总分")
    parser.add_argument("--intraday", action="store_true", help="改为生成盘中异动观察，而不是早报")
    parser.add_argument("--no-cache", action="store_true", help="禁用缓存")
    parser.add_argument("--allow-akshare-fallback", action="store_true", help="直连接口失败时允许使用 AkShare 慢回退")
    parser.add_argument("--send-telegram", action="store_true", help="发送 Telegram 摘要")
    parser.add_argument("--env", default=".env", help="环境变量文件")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "intraday":
        return run_intraday(argv[1:])
    args = parse_args(argv)
    if args.intraday:
        return run_intraday(
            _intraday_argv_from_morning(args),
        )
    config = load_config(args.config)
    report_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else shanghai_now().date()
    top_n = args.top or int(config.report.get("default_top_n", 5))
    lookback_days = args.lookback_days or int(config.report.get("default_lookback_days", 420))

    provider = _make_provider(args)
    result = rank_report(
        config.themes,
        provider,
        report_date=report_date,
        top_n=top_n,
        lookback_days=lookback_days,
        skip_news=args.skip_news,
        max_themes=args.max_themes,
        skip_macro=args.skip_macro,
        legacy_weights=args.legacy_weights,
    )
    markdown = render_markdown(result, config.report.get("risk_note", "本报告不构成投资建议。"))
    md_path, json_path = write_outputs(result, markdown, args.output)
    print(f"已生成报告: {Path(md_path).resolve()}")
    print(f"已生成结构化数据: {Path(json_path).resolve()}")

    if args.send_telegram:
        load_env(args.env)
        send_telegram(markdown)
        print("已发送 Telegram 摘要")

    return 0


def run_intraday(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="ashare_us_catalyst.cli intraday", description="生成 A 股盘中异动观察")
    parser.add_argument("--config", default="config/themes.json", help="板块和候选池配置")
    parser.add_argument("--output", default="reports", help="报告输出目录")
    parser.add_argument("--cache", default=".cache", help="行情缓存目录")
    parser.add_argument("--date", default=None, help="报告标签日期，格式 YYYY-MM-DD，默认今天。行情仍是当前可得数据")
    parser.add_argument("--sample-data", action="store_true", help="使用离线样例数据")
    parser.add_argument("--no-cache", action="store_true", help="禁用缓存")
    parser.add_argument("--allow-akshare-fallback", action="store_true", help="直连接口失败时允许使用 AkShare 慢回退")
    parser.add_argument("--top-sectors", type=int, default=8, help="板块涨幅榜数量")
    parser.add_argument("--move-threshold", type=float, default=5.0, help="候选池大幅波动阈值，单位百分比")
    parser.add_argument("--volume-ratio", type=float, default=2.0, help="放量异动量比阈值")
    parser.add_argument("--policy-hours", type=float, default=18.0, help="政策快讯回看小时数")
    parser.add_argument("--send-telegram", action="store_true", help="发送 Telegram 摘要")
    parser.add_argument("--env", default=".env", help="环境变量文件")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    report_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else shanghai_now().date()
    provider = _make_provider(args)
    result = build_intraday_report(
        config.themes,
        provider,
        report_date=report_date,
        top_sectors=args.top_sectors,
        move_threshold=args.move_threshold,
        volume_ratio_threshold=args.volume_ratio,
        policy_hours=args.policy_hours,
    )
    markdown = render_intraday_markdown(result)
    md_path, json_path = write_intraday_outputs(result, markdown, args.output)
    print(f"已生成盘中观察: {md_path.resolve()}")
    print(f"已生成结构化数据: {json_path.resolve()}")
    if args.send_telegram:
        load_env(args.env)
        send_telegram(markdown)
        print("已发送 Telegram 摘要")
    return 0


def _make_provider(args: argparse.Namespace):
    if args.sample_data:
        return SampleProvider()
    return AkshareProvider(args.cache, use_cache=not args.no_cache, allow_akshare_fallback=args.allow_akshare_fallback)


def _intraday_argv_from_morning(args: argparse.Namespace) -> list[str]:
    argv = ["--config", args.config, "--output", args.output, "--cache", args.cache, "--env", args.env]
    if args.date:
        argv.extend(["--date", args.date])
    if args.sample_data:
        argv.append("--sample-data")
    if args.no_cache:
        argv.append("--no-cache")
    if args.allow_akshare_fallback:
        argv.append("--allow-akshare-fallback")
    if args.send_telegram:
        argv.append("--send-telegram")
    return argv


if __name__ == "__main__":
    raise SystemExit(main())
