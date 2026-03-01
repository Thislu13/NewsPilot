"""
投资策略分析服务 - 使用 Agent 架构进行投资分析

这是一个示例工作流，展示如何使用 InvestmentAgent 进行智能选股分析。

Usage:
    # 单次分析
    python -m src.workflows.run_investment_analysis --mode once

    # 定时调度
    python -m src.workflows.run_investment_analysis --mode schedule --report-time 09:00

    # 使用不同模型
    python -m src.workflows.run_investment_analysis --model-name deepseek
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, time, timedelta

from src.intelligence.investment_agent import InvestmentAgent

# Add project root to path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

def parse_report_time(value: str) -> time:
    """解析时间"""
    try:
        hour_str, minute_str = value.split(":", 1)
        return time(int(hour_str), int(minute_str))
    except Exception as exc:
        raise argparse.ArgumentTypeError("report_time must be HH:MM") from exc


async def main(
    model_name: str,
    save_dir: str,
    report_time: time = time(9, 0),
    use_agent: bool = True,
):
    """
    执行一次投资策略分析

    Args:
        model_name: 使用的模型名称
        save_dir: 保存目录
        report_time: 报告时间（用于计算时间范围）
        use_agent: 是否使用 Agent 架构
    """
    print(f"\n{'='*60}")
    print(f"[investment_analysis] 开始分析 [model={model_name}, use_agent={use_agent}]")
    print(f"{'='*60}")

    # 计算时间范围
    now = datetime.now()
    today_cutoff = datetime.combine(now.date(), report_time)

    if now.time() < report_time:
        print(f"[investment_analysis] 早于报告时间: {now.strftime('%H:%M')} < {report_time.strftime('%H:%M')}")

    yesterday_cutoff = today_cutoff - timedelta(days=1)
    time_range = (yesterday_cutoff, today_cutoff)

    print(f"[investment_analysis] 分析时间范围: {yesterday_cutoff.strftime('%Y-%m-%d %H:%M')} -> {today_cutoff.strftime('%Y-%m-%d %H:%M')}")
    print(f"[investment_analysis] 输出目录: {save_dir}")
    print()

    # 构建输出路径
    date_str = today_cutoff.strftime("%Y-%m-%d")
    output_dir = os.path.join(save_dir, date_str)
    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(output_dir, "investment_analysis_agent.md")

    try:
        if use_agent:
            # 使用新的 Agent 架构
            print("[*] 使用 Agent 架构进行分析...")
            print("[*] Agent 将自动获取新闻并进行多轮推理")
            print()

            agent = InvestmentAgent(
                model_name=model_name,
                max_iterations=10,
                temperature=0.7
            )

            # 定义进度回调
            def on_progress(msg: str):
                print(f"  [Agent] {msg}")

            # 执行分析
            result = await agent.analyze_with_news(
                time_range=time_range,
                output_path=output_path
            )

            if result["status"] == "success":
                print()
                print(f"[✓] 分析完成")
                print(f"[✓] 工具调用次数: {len(result['tools_used'])}")
                print(f"[✓] 迭代次数: {result['iteration_count']}")
                print(f"[✓] 报告已保存至: {result['output_path']}")
            else:
                print(f"[!] 分析失败")

        else:
            # 使用旧的简单分析方式
            print("[*] 使用传统分析方式...")
            # 这里可以调用旧的 InvestmentAnalyzer
            from src.intelligence.investment_analyzer import InvestmentAnalyzer

            analyzer = InvestmentAnalyzer(model_name=model_name)
            result = await analyzer.analyze_investment_opportunities(
                time_range=time_range,
                output_path=output_path.replace("_agent", "")
            )

            if result["status"] == "success":
                print(f"[✓] 分析完成，共分析 {result['news_count']} 条新闻")
                print(f"[✓] 报告已保存至: {result['output_path']}")
            elif result["status"] == "no_news":
                print("[!] 没有找到相关新闻")
            else:
                print(f"[!] 分析失败: {result.get('error')}")

    except Exception as e:
        print(f"[!] 错误: {e}")
        import traceback
        traceback.print_exc()

    print(f"{'='*60}\n")


async def scheduler(
    save_dir: str,
    model_name: str = "gemini",
    report_time: time = time(9, 0),
    use_agent: bool = True,
):
    """
    定时调度器

    Args:
        save_dir: 保存目录
        model_name: 模型名称
        report_time: 报告时间
        use_agent: 是否使用 Agent 架构
    """
    print(
        f"[investment_analysis] 调度器启动; report_time={report_time.strftime('%H:%M')}, use_agent={use_agent}"
    )

    while True:
        now = datetime.now()
        target_time = datetime.combine(now.date(), report_time)

        if now.time() > report_time:
            target_time += timedelta(days=1)

        wait_seconds = (target_time - now).total_seconds()
        print(f"[investment_analysis] 等待 {wait_seconds:.0f}秒 直到 {target_time.strftime('%Y-%m-%d %H:%M')}")

        await asyncio.sleep(wait_seconds)

        print(f"[investment_analysis] 触发定时分析 at {datetime.now()}")
        await main(
            model_name=model_name,
            save_dir=save_dir,
            report_time=report_time,
            use_agent=use_agent,
        )

        # 等待60秒后再次检查
        await asyncio.sleep(60)


def build_arg_parser() -> argparse.ArgumentParser:
    """构建参数解析器"""
    parser = argparse.ArgumentParser(
        description="运行投资策略分析服务 (基于 Agent 架构)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用 Agent 进行单次分析
  python -m src.workflows.run_investment_analysis --mode once

  # 使用传统方式
  python -m src.workflows.run_investment_analysis --mode once --no-agent

  # 定时调度（每天早上9点）
  python -m src.workflows.run_investment_analysis --mode schedule --report-time 09:00

  # 使用 DeepSeek 模型
  python -m src.workflows.run_investment_analysis --model-name deepseek
        """
    )

    parser.add_argument(
        "--mode",
        choices=["schedule", "once"],
        default="once",
        help="运行模式: schedule=定时调度, once=单次执行"
    )

    parser.add_argument(
        "--model-name",
        default="gemini",
        help="使用的模型名称 (gemini/deepseek/qwen)"
    )

    parser.add_argument(
        "--report-time",
        type=parse_report_time,
        default=time(9, 0),
        help="报告时间 (HH:MM格式)"
    )

    parser.add_argument(
        "--save-dir",
        default=os.path.join(PROJECT_ROOT, "data", "investment_analysis"),
        help="保存目录"
    )

    parser.add_argument(
        "--no-agent",
        action="store_true",
        help="不使用 Agent 架构，使用传统分析方式"
    )

    return parser


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    args = build_arg_parser().parse_args()

    use_agent = not args.no_agent

    try:
        if args.mode == "once":
            # 单次执行
            asyncio.run(
                main(
                    model_name=args.model_name,
                    save_dir=args.save_dir,
                    report_time=args.report_time,
                    use_agent=use_agent,
                )
            )
        else:
            # 定时调度
            asyncio.run(
                scheduler(
                    save_dir=args.save_dir,
                    model_name=args.model_name,
                    report_time=args.report_time,
                    use_agent=use_agent,
                )
            )

    except KeyboardInterrupt:
        print("\n[investment_analysis] 服务已停止")
