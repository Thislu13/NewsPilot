# src/workflows/run_daily_report.py
"""
生成每日报表 (Daily Report Task)
职责：
1. 计算正确的统计时间窗口 (昨天 8:00 BM - 今天 8:00 AM)
2. 调用 Analyzer 生成全量报表
该脚本通常由系统定时任务 (Cron/Task Scheduler) 调用，也可手动运行。
"""
import asyncio
import os
import sys
from datetime import datetime, time, timedelta

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.append(project_root)

from src.intelligence.new_analyzer import NewsAnalyzer
# Import Distribution
try:
    from src.distribution.email_sender import send_daily_report_email
except ImportError:
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), '../../'))
    from src.distribution.email_sender import send_daily_report_email

# Config

async def main(model_name: str, save_dir: str, report_time: time = time(8, 0), enable_email: bool = False):
    """
    运行日报生成任务
    :param save_dir: 报告保存目录
    :param model_name: 使用的模型名称 (gemini, deepseek, etc.)
    :param report_time: 结算时间点 (默认 08:00)
    :param enable_email: 是否开启邮件分发
    """
    print(f"\n🚀 Starting Daily Report Task [Model: {model_name}]")
    
    analyzer = NewsAnalyzer(model_name=model_name)
    
    # Calculate Time Window (Yesterday 8:00 AM -> Today 8:00 AM)
    now = datetime.now()
    today_cutoff = datetime.combine(now.date(), report_time)
    
    # Check if run before the cutoff time
    if now.time() < report_time:
        print(f"⚠️  Early Run: Current time {now.strftime('%H:%M')} < {report_time}. Generating PREVIEW.")
    
    yesterday_cutoff = today_cutoff - timedelta(days=1)
    
    print(f"📅 Time Window: {yesterday_cutoff} -> {today_cutoff}")
    print(f"📂 Output Dir: {save_dir}\n")
    save_md_path = os.path.join(save_dir, "markdown")
    save_html_path = os.path.join(save_dir, "html")
    save_pdf_path = os.path.join(save_dir, "pdf")

    try:
        results = await analyzer.generate_all_daily_reports(
            target_date=today_cutoff.date(),
            time_range=(yesterday_cutoff, today_cutoff),
            save_md_list="ALL",  # 默认保存所有 Markdown
            save_html_list=["total"],    # 默认只保存总日报 HTML
            save_pdf_list="ALL_CATEGORIES",    # 保存所有 PDF (含 total 和分领域)
            md_output_dir=save_md_path,
            html_output_dir=save_html_path,
            pdf_output_dir=save_pdf_path
        )
        print("\n✅ Report Generation Completed.")
        
        # --- Email Distribution ---
        if enable_email:
            try:
                print(f"[*] Starting Email Distribution...")
                
                # 1. Body: Total HTML
                total_html_path = results.get("total", {}).get("html_path")
                
                # 2. Attachments: All PDFs (Categories + Total)
                attachment_paths = []
                
                # Add Total PDF
                if results.get("total", {}).get("pdf_path"):
                    attachment_paths.append(results["total"]["pdf_path"])
                    
                # Add Category PDFs
                for cat, res in results.items():
                    if cat == "total": continue
                    if res.get("pdf_path"):
                        attachment_paths.append(res["pdf_path"])
                
                subject = f"NewsPilot 全领域深度日报 ({today_cutoff.date()})"
                
                # 只有当有内容时才发送
                if total_html_path or attachment_paths:
                    send_daily_report_email(subject, total_html_path, attachment_paths)
                else:
                    print("⚠️ 没有生成 HTML 或 PDF，跳过发送邮件。")

            except Exception as e:
                print(f"❌ 邮件发送流程异常: {e}")
                
    except Exception as e:
        print(f"\n❌ Error: {e}")

async def scheduler(save_dir: str, model_name: str = "gemini", report_time: time = time(8, 0), enable_email: bool = False):
    """
    定时调度任务：每天指定时间运行
    """
    print(f"\n🔁 Starting Scheduler Mode. Target time: {report_time} daily. Email: {enable_email}")
    
    while True:
        now = datetime.now()
        target_time = datetime.combine(now.date(), report_time)
        
        # If today's target time has passed, schedule for tomorrow
        if now.time() > report_time:
             target_time += timedelta(days=1)
        
        wait_seconds = (target_time - now).total_seconds()
        print(f"⏳ Sleeping for {wait_seconds:.0f}s (until {target_time})...")
        
        await asyncio.sleep(wait_seconds)
        
        # Run the task
        print(f"\n⏰ Waking up for scheduled run at {datetime.now()}")
        await main(model_name="gemini", save_dir=DEFAULT_SAVE_DIR, report_time=time(8, 0), enable_email=enable_email)
        
        # Wait a bit to prevent re-triggering immediately
        await asyncio.sleep(60)

if __name__ == "__main__":
    if sys.platform.startswith('win'):
        # 解决 Windows 上 EventLoop 关闭时的 RuntimeError
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    try:
        # Default Configuration: Output to project_root/data/reports/...
        DEFAULT_SAVE_DIR = os.path.join(project_root, "data", 'daily_reports')
        
        #如果想生成昨天的报表，可以取消下面这行注释，并注释掉scheduler的调用
        # asyncio.run(main(save_dir=DEFAULT_SAVE_DIR, model_name="gemini", report_time=time(8, 0), enable_email=True))

        # 启动定时调度器
        asyncio.run(scheduler(
            save_dir=DEFAULT_SAVE_DIR,
            model_name="gemini",
            report_time=time(8, 0),
            enable_email=True # 默认开启邮件推送
        ))
    except KeyboardInterrupt:
        print("\n👋 Scheduler Stopped.")
