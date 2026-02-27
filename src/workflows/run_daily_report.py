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
):
    print(f"\n[daily_report] starting [model={model_name}]")
    analyzer = NewsAnalyzer(model_name=model_name)

    now = datetime.now()
    today_cutoff = datetime.combine(now.date(), report_time)
    if now.time() < report_time:
        print(
            f"[daily_report] early run: now={now.strftime('%H:%M')} < cutoff={report_time.strftime('%H:%M')}"
        )

    yesterday_cutoff = today_cutoff - timedelta(days=1)
    print(f"[daily_report] window: {yesterday_cutoff} -> {today_cutoff}")
    print(f"[daily_report] output_dir: {save_dir}")

    save_md_path = os.path.join(save_dir, "markdown")
    save_html_path = os.path.join(save_dir, "html")
    save_pdf_path = os.path.join(save_dir, "pdf")

    try:
        results = await analyzer.generate_all_daily_reports(
            target_date=today_cutoff.date(),
            time_range=(yesterday_cutoff, today_cutoff),
            save_md_list="ALL",
            save_html_list=["total"],
            save_pdf_list="ALL_CATEGORIES",
            md_output_dir=save_md_path,
            html_output_dir=save_html_path,
            pdf_output_dir=save_pdf_path,
        )
        print("[daily_report] report generation completed.")

        if enable_email:
            print("[daily_report] email distribution enabled.")
            total_html_path = results.get("total", {}).get("html_path")
            attachment_paths = []
            if results.get("total", {}).get("pdf_path"):
                attachment_paths.append(results["total"]["pdf_path"])
            for cat, res in results.items():
                if cat == "total":
                    continue
                if res.get("pdf_path"):
                    attachment_paths.append(res["pdf_path"])

            subject = f"NewsPilot Daily Report ({today_cutoff.date()})"
            if total_html_path or attachment_paths:
                send_daily_report_email(
                    subject=subject,
                    html_body_path=total_html_path,
                    attachment_paths=attachment_paths,
                    service_name="daily_report",
                )
            else:
                print("[daily_report] no HTML/PDF generated, skip email.")
    except Exception as e:
        print(f"[daily_report] error: {e}")


async def scheduler(
    save_dir: str,
    model_name: str = "gemini",
    report_time: time = time(8, 0),
    enable_email: bool = False,
):
    print(
        f"[daily_report] scheduler started; report_time={report_time.strftime('%H:%M')}, "
        f"enable_email={enable_email}"
    )
    while True:
        now = datetime.now()
        target_time = datetime.combine(now.date(), report_time)
        if now.time() > report_time:
            target_time += timedelta(days=1)

        wait_seconds = (target_time - now).total_seconds()
        print(f"[daily_report] sleeping {wait_seconds:.0f}s until {target_time}")
        await asyncio.sleep(wait_seconds)

        print(f"[daily_report] triggering scheduled run at {datetime.now()}")
        await main(
            model_name=model_name,
            save_dir=save_dir,
            report_time=report_time,
            enable_email=enable_email,
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
    return parser


if __name__ == "__main__":
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
                )
            )
        else:
            asyncio.run(
                scheduler(
                    save_dir=args.save_dir,
                    model_name=args.model_name,
                    report_time=args.report_time,
                    enable_email=args.enable_email,
                )
            )
    except KeyboardInterrupt:
        print("[daily_report] stopped.")
