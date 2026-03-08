#
# Author: Claude Code
# Date: 2026-03-08
# Description: 整合渲染器 - 将投资分析和日报内容整合为统一报告
#

import re
from datetime import date
from typing import Dict, Any


class IntegratedReportRenderer:
    """
    整合渲染器
    职责：将投资分析报告和Total日报整合为统一的投资版日报

    报告结构：
    1. 标题和元数据
    2. 投资分析执行摘要
    3. Total日报内容
    4. 投资分析详细内容（推荐股票列表）
    5. 风险提示和免责声明
    """

    def render(
        self,
        investment_md: str,
        total_report_md: str,
        date: date
    ) -> str:
        """
        渲染整合报告

        Args:
            investment_md: 投资报告完整Markdown
            total_report_md: Total日报Markdown
            date: 报告日期

        Returns:
            整合后的Markdown文本
        """
        # 1. 提取投资报告的各个部分
        investment_parts = self._parse_investment_report(investment_md)

        # 2. 提取Total日报的内容（去除标题）
        total_content = self._extract_total_content(total_report_md)

        # 3. 组装整合报告
        integrated_md = self._assemble_report(
            investment_parts=investment_parts,
            total_content=total_content,
            date=date
        )

        return integrated_md

    def _parse_investment_report(self, investment_md: str) -> Dict[str, str]:
        """
        解析投资报告，提取各个部分

        Returns:
            {
                "header": "标题和元数据",
                "summary": "执行摘要",
                "stock_list": "推荐股票列表（详细分析）",
                "risk_warning": "风险提示",
                "disclaimer": "免责声明"
            }
        """
        parts = {}

        # 提取标题和元数据（从开头到第一个 ---）
        header_match = re.search(r'^(.*?)\n---', investment_md, re.DOTALL)
        if header_match:
            parts["header"] = header_match.group(1).strip()

        # 提取执行摘要（## 🎯 执行摘要 到下一个 ##）
        summary_match = re.search(
            r'## 🎯 执行摘要\n(.*?)(?=\n## |\Z)',
            investment_md,
            re.DOTALL
        )
        if summary_match:
            parts["summary"] = summary_match.group(1).strip()

        # 提取推荐股票列表（## 💎 推荐股票列表 到 ## ⚠️ 风险提示）
        stock_list_match = re.search(
            r'## 💎 推荐股票列表\n(.*?)(?=\n## ⚠️ 风险提示|\Z)',
            investment_md,
            re.DOTALL
        )
        if stock_list_match:
            parts["stock_list"] = stock_list_match.group(1).strip()

        # 提取风险提示（## ⚠️ 风险提示 到 ## 📝 免责声明）
        risk_match = re.search(
            r'## ⚠️ 风险提示\n(.*?)(?=\n## 📝 免责声明|\Z)',
            investment_md,
            re.DOTALL
        )
        if risk_match:
            parts["risk_warning"] = risk_match.group(1).strip()

        # 提取免责声明（## 📝 免责声明 到结尾）
        disclaimer_match = re.search(
            r'## 📝 免责声明\n(.*?)(?=\n---|\Z)',
            investment_md,
            re.DOTALL
        )
        if disclaimer_match:
            parts["disclaimer"] = disclaimer_match.group(1).strip()

        return parts

    def _extract_total_content(self, total_report_md: str) -> str:
        """
        提取Total日报的主要内容（去除标题和元数据）

        Returns:
            日报主要内容
        """
        # 去除标题行（# 开头）和元数据（> 开头）
        lines = total_report_md.split('\n')
        content_lines = []
        skip_header = True

        for line in lines:
            # 跳过标题和元数据
            if skip_header:
                if line.startswith('# ') or line.startswith('> ') or line.strip() == '':
                    continue
                elif line.strip() == '---':
                    skip_header = False
                    continue

            content_lines.append(line)

        return '\n'.join(content_lines).strip()

    def _assemble_report(
        self,
        investment_parts: Dict[str, str],
        total_content: str,
        date: date
    ) -> str:
        """
        组装整合报告

        结构：
        1. 标题和元数据
        2. 投资分析执行摘要
        3. Total日报内容
        4. 推荐股票详细分析
        5. 风险提示和免责声明
        """
        sections = []

        # 1. 标题和元数据
        header = f"""# 📊 NewsPilot 投资版日报 - {date.strftime('%Y-%m-%d')}

> 生成时间：{date.strftime('%Y-%m-%d')}
> 报告类型：投资分析 + 新闻日报
> 数据来源：多源新闻聚合 + AI深度分析

---
"""
        sections.append(header)

        # 2. 投资分析执行摘要
        if investment_parts.get("summary"):
            sections.append("## 🎯 投资分析执行摘要\n")
            sections.append(investment_parts["summary"])
            sections.append("\n---\n")

        # 3. Total日报内容
        sections.append("## 📰 今日新闻深度分析\n")
        sections.append(total_content)
        sections.append("\n---\n")

        # 4. 推荐股票详细分析
        if investment_parts.get("stock_list"):
            sections.append("## 💎 推荐股票详细分析\n")
            sections.append(investment_parts["stock_list"])
            sections.append("\n---\n")

        # 5. 风险提示
        if investment_parts.get("risk_warning"):
            sections.append("## ⚠️ 风险提示\n")
            sections.append(investment_parts["risk_warning"])
            sections.append("\n---\n")

        # 6. 免责声明
        if investment_parts.get("disclaimer"):
            sections.append("## 📝 免责声明\n")
            sections.append(investment_parts["disclaimer"])
            sections.append("\n---\n")

        # 7. 页脚
        footer = f"""
### ℹ️ 关于本报告
本报告由开源项目 **[NewsPilot](https://github.com/Thislu13/NewsPilot)** 自动生成。
NewsPilot 是一个**开源的自动化情报分析系统**，利用 LLM 技术对多源新闻进行聚合、筛选、摘要与深度分析。
欢迎 Star ⭐ 关注项目发展。

*报告生成时间：{date.strftime('%Y-%m-%d')}*
"""
        sections.append(footer)

        return '\n'.join(sections)

