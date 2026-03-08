#
# Author: Claude Code
# Date: 2026-03-08
# Description: 投资分析器 - 基于日报生成投资分析报告
#

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from src.module.agent.simple_agent import SimpleAgent
from src.module.agent.providers.litellm_provider import LiteLLMProvider
from config import keys
from src.custom_logging import get_logger

logger = get_logger(__name__)


class InvestmentAnalyzer:
    """
    投资分析器
    职责：基于每日新闻日报，使用 SimpleAgent 和 investment-report-skill 生成投资分析报告

    设计理念：
    1. 封装 SimpleAgent，保持与 NewsAnalyzer/ZhihuAnalyzer 一致的接口
    2. 使用 investment-report-skill 控制整个流程
    3. Agent 自主决策，完成从读取新闻到生成报告的全过程
    """

    def __init__(self, model_name: str = "gemini", workspace: Path = None):
        """
        初始化投资分析器

        Args:
            model_name: 使用的模型 (gemini/deepseek/qwen)
            workspace: 工作空间路径
        """
        self.model_name = model_name
        self.workspace = workspace or Path.cwd()

        # 初始化 LLM Provider
        self.provider = self._init_provider()

        # 初始化 SimpleAgent
        self.agent = SimpleAgent(
            provider=self.provider,
            workspace=self.workspace,
            enable_spawn=True,  # 启用 sub-agent 并行分析
            max_iterations=50,  # 增加迭代次数，因为流程更复杂
            temperature=1.0,  # 降低温度提高稳定性
            max_tokens=16384  # 增加 token 限制
        )

    def _init_provider(self) -> LiteLLMProvider:
        """初始化 LLM Provider"""
        api_key_map = {
            "gemini": keys.gemini_api,
            "deepseek": keys.deepseek_api,
            "qwen": keys.qwen_api,
        }

        model_id_map = {
            "gemini": "gemini/gemini-3.1-pro-preview",
            "deepseek": "deepseek/deepseek-chat",
            "qwen": "qwen/qwen-plus",
        }

        return LiteLLMProvider(
            api_key=api_key_map.get(self.model_name),
            default_model=model_id_map.get(self.model_name)
        )

    async def generate_investment_report(
        self,
        date: str,
        output_dir: Optional[str] = None,
        max_stocks: int = 8
    ) -> Dict[str, Any]:
        """
        生成投资日报（主入口）

        Args:
            date: 分析日期 (YYYY-MM-DD)
            output_dir: 输出目录
            max_stocks: 最多分析的股票数量

        Returns:
            {
                "date": "2026-01-30",
                "report_md": "...",
                "report_path": "..."
            }
        """
        logger.info(f"[InvestmentAnalyzer] 开始生成投资日报: {date}")

        try:
            # 构建简单的任务描述，让 skill 控制流程
            query = self._build_task_query(date, max_stocks)

            # 一次性调用 agent，使用 investment-report-skill
            logger.info(f"[InvestmentAnalyzer] 调用 Agent，使用 investment-report-skill")
            report_md = await self.agent.ask(
                question=query,
                skill_names=["investment-report-skill"]
            )

            # 保存报告
            report_path = self._save_report(date, report_md, output_dir)

            logger.info(f"[InvestmentAnalyzer] 报告已保存: {report_path}")

            return {
                "date": date,
                "report_md": report_md,
                "report_path": report_path
            }

        except Exception as e:
            logger.error(f"[InvestmentAnalyzer] 生成报告失败: {e}")
            import traceback
            traceback.print_exc()
            return {"error": str(e), "date": date}

    def _build_task_query(self, date: str, max_stocks: int) -> str:
        """
        构建任务查询

        简单明确，让 skill 控制具体流程
        """
        return f"""
请生成 {date} 的投资日报。

## 任务要求

1. 日报目录：data/daily_reports/{date}/markdown/
2. 最多分析 {max_stocks} 只股票
3. 只保留"买入"建议的股票
4. 按照报告模板格式输出

## 重要提示

- 你有完整的 investment-report-skill 指导你完成任务
- 充分利用所有可用工具（read_file, list_dir, spawn, 股票数据工具等）
- Sub-agent 必须使用 value-investment-strategy skill
- 严格按照模板格式输出最终报告

现在开始执行任务。
"""

    def _save_report(
        self,
        date: str,
        report_md: str,
        output_dir: Optional[str] = None
    ) -> str:
        """保存报告"""
        if output_dir is None:
            output_dir = os.path.join(self.workspace, "data", "investment_reports")

        # 创建日期子目录
        date_dir = os.path.join(output_dir, date)
        os.makedirs(date_dir, exist_ok=True)

        # 保存文件
        report_path = os.path.join(date_dir, f"{date}_投资日报.md")

        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report_md)
            logger.info(f"[InvestmentAnalyzer] 报告已保存: {report_path}")
        except Exception as e:
            logger.error(f"[InvestmentAnalyzer] 保存报告失败: {e}")

        return report_path


# 测试代码
if __name__ == "__main__":
    async def main():
        analyzer = InvestmentAnalyzer(
            model_name="gemini",
            workspace=Path("E:/code/NewsPilot")
        )

        result = await analyzer.generate_investment_report(
            date="2026-03-08",
            max_stocks=5
        )

        print(f"\n生成结果:")
        print(f"- 日期: {result.get('date')}")
        if "error" in result:
            print(f"- 错误: {result['error']}")
        else:
            print(f"- 报告路径: {result.get('report_path')}")

    asyncio.run(main())
