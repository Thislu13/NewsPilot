"""
投资日报生成工作流

使用 InvestmentAnalyzer 生成投资分析报告

Usage:
    python -m src.workflows.run_investment_report --date 2026-01-30
    python -m src.workflows.run_investment_report --date 2026-01-30 --model gemini --max-stocks 8
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.intelligence.investment_analyzer import InvestmentAnalyzer


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="投资日报生成系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--date",
        type=str,
        help="分析日期 (YYYY-MM-DD)，默认为昨天"
    )

    parser.add_argument(
        "--model",
        type=str,
        default="gemini",
        choices=["gemini", "deepseek", "qwen"],
        help="使用的模型名称"
    )

    parser.add_argument(
        "--max-stocks",
        type=int,
        default=8,
        help="最多分析的股票数量"
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="报告保存目录"
    )

    args = parser.parse_args()

    # 计算日期
    if args.date:
        date = args.date
    else:
        # 默认使用昨天
        yesterday = datetime.now() - timedelta(days=1)
        date = yesterday.strftime("%Y-%m-%d")

    print(f"\n{'='*60}")
    print(f"投资日报生成系统")
    print(f"{'='*60}")
    print(f"日期: {date}")
    print(f"模型: {args.model}")
    print(f"最多股票数: {args.max_stocks}")
    print(f"{'='*60}\n")

    try:
        # 初始化分析器
        analyzer = InvestmentAnalyzer(
            model_name=args.model,
            workspace=Path(PROJECT_ROOT)
        )

        # 生成报告
        result = await analyzer.generate_investment_report(
            date=date,
            output_dir=args.output_dir,
            max_stocks=args.max_stocks
        )

        # 输出结果
        if "error" in result:
            print(f"\n[✗] 生成失败: {result['error']}")
            sys.exit(1)
        else:
            print(f"\n[✓] 投资日报生成成功")
            print(f"[✓] 识别股票: {len(result.get('stocks', []))} 只")
            print(f"[✓] 完成分析: {len(result.get('analyses', []))} 只")
            print(f"[✓] 报告路径: {result.get('report_path')}")

            # 显示股票列表
            print(f"\n推荐股票:")
            for i, stock in enumerate(result.get('stocks', []), 1):
                print(f"  {i}. {stock['name']} ({stock['symbol']})")
                print(f"     理由: {stock['reason'][:50]}...")

    except KeyboardInterrupt:
        print("\n[!] 任务已中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n[!] 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())
