"""
Daily report workflow entry.
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, time, timedelta

# Add project root to path for direct execution.
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.distribution.email_sender import send_daily_report_email
from src.intelligence.new_analyzer import NewsAnalyzer
from src.custom_logging import get_logger, setup_logging

logger = get_logger(__name__)


def parse_bool(value: str) -> bool:
    v = (value or "").strip().lower()
    if v in {"1", "true", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"Invalid boolean value: {value}")


def parse_report_time(value: str) -> time:
    try:
        hour_str, minute_str = value.split(":", 1)
        return time(int(hour_str), int(minute_str))
    except Exception as exc:
        raise argparse.ArgumentTypeError("report_time must be HH:MM") from exc


async def main(
    model_name: str,
    save_dir: str,
    report_time: time = time(8, 0),
    enable_email: bool = False,
    enable_investment: bool = False,
    investment_model: str = "gemini",
    max_stocks: int = 8,
):
    logger.info(f"[daily_report] starting [model={model_name}]")
    analyzer = NewsAnalyzer(model_name=model_name)

    now = datetime.now()
    today_cutoff = datetime.combine(now.date(), report_time)
    if now.time() < report_time:
        logger.info(
            f"[daily_report] early run: now={now.strftime('%H:%M')} < cutoff={report_time.strftime('%H:%M')}"
        )

    yesterday_cutoff = today_cutoff - timedelta(days=1)
    logger.info(f"[daily_report] window: {yesterday_cutoff} -> {today_cutoff}")
    logger.info(f"[daily_report] output_dir: {save_dir}")

    save_md_path = os.path.join(save_dir, "markdown")
    save_html_path = os.path.join(save_dir, "html")
    save_pdf_path = os.path.join(save_dir, "pdf")

    try:
        results = await analyzer.generate_all_daily_reports(
            target_date=today_cutoff.date(),
            time_range=(yesterday_cutoff, today_cutoff),
            save_md_list="ALL",
            save_html_list=["integrated"] if enable_investment else ["total"],
            save_pdf_list="ALL_CATEGORIES",
            md_output_dir=save_md_path,
            html_output_dir=save_html_path,
            pdf_output_dir=save_pdf_path,
            enable_investment_analysis=enable_investment,
            investment_model=investment_model,
            max_stocks=max_stocks,
        )
        logger.info("[daily_report] report generation completed.")

        if enable_email:
            logger.info("[daily_report] email distribution enabled.")

            # 优先使用整合版
            if "integrated" in results:
                html_path = results["integrated"].get("html_path")
                subject = f"NewsPilot 投资版日报 ({today_cutoff.date()})"
            else:
                html_path = results.get("total", {}).get("html_path")
                subject = f"NewsPilot Daily Report ({today_cutoff.date()})"

            # 附件: 各领域PDF（不包含整合版或total的PDF）
            attachment_paths = []
            for cat, res in results.items():
                if cat not in ["total", "integrated"] and res.get("pdf_path"):
                    attachment_paths.append(res["pdf_path"])

            if html_path or attachment_paths:
                send_daily_report_email(
                    subject=subject,
                    html_body_path=html_path,
                    attachment_paths=attachment_paths,
                    service_name="daily_report",
                )
            else:
                logger.warning("[daily_report] no HTML/PDF generated, skip email.")
    except Exception as e:
        logger.error(f"[daily_report] error: {e}", exc_info=True)


async def scheduler(
    save_dir: str,
    model_name: str = "gemini",
    report_time: time = time(8, 0),
    enable_email: bool = False,
    enable_investment: bool = False,
    investment_model: str = "gemini",
    max_stocks: int = 8,
):
    logger.info(
        f"[daily_report] scheduler started; report_time={report_time.strftime('%H:%M')}, "
        f"enable_email={enable_email}"
    )
    while True:
        now = datetime.now()
        target_time = datetime.combine(now.date(), report_time)
        if now.time() > report_time:
            target_time += timedelta(days=1)

        wait_seconds = (target_time - now).total_seconds()
        logger.info(f"[daily_report] sleeping {wait_seconds:.0f}s until {target_time}")
        await asyncio.sleep(wait_seconds)

        logger.info(f"[daily_report] triggering scheduled run at {datetime.now()}")
        await main(
            model_name=model_name,
            save_dir=save_dir,
            report_time=report_time,
            enable_email=enable_email,
            enable_investment=enable_investment,
            investment_model=investment_model,
            max_stocks=max_stocks,
        )
        await asyncio.sleep(60)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run daily report workflow.")
    parser.add_argument("--enable-email", type=parse_bool, default=True)
    parser.add_argument("--mode", choices=["schedule", "once"], default="schedule")
    parser.add_argument("--model-name", default="gemini")
    parser.add_argument("--report-time", type=parse_report_time, default=time(8, 0))
    parser.add_argument(
        "--save-dir",
        default=os.path.join(PROJECT_ROOT, "data", "daily_reports"),
    )
    # 投资分析参数
    parser.add_argument(
        "--enable-investment",
        type=parse_bool,
        default=False,
        help="是否启用投资分析（默认False）"
    )
    parser.add_argument(
        "--investment-model",
        default="gemini",
        help="投资分析使用的模型（默认gemini）"
    )
    parser.add_argument(
        "--max-stocks",
        type=int,
        default=8,
        help="最多分析的股票数量（默认8）"
    )
    return parser


if __name__ == "__main__":
    # 初始化日志系统
    setup_logging()

    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    args = build_arg_parser().parse_args()
    try:
        if args.mode == "once":
            asyncio.run(
                main(
                    model_name=args.model_name,
                    save_dir=args.save_dir,
                    report_time=args.report_time,
                    enable_email=args.enable_email,
                    enable_investment=args.enable_investment,
                    investment_model=args.investment_model,
                    max_stocks=args.max_stocks,
                )
            )
        else:
            asyncio.run(
                scheduler(
                    model_name=args.model_name,
                    save_dir=args.save_dir,
                    report_time=args.report_time,
                    enable_email=args.enable_email,
                    enable_investment=args.enable_investment,
                    investment_model=args.investment_model,
                    max_stocks=args.max_stocks,
                )
            )
    except KeyboardInterrupt:
        logger.info("[daily_report] stopped.")
