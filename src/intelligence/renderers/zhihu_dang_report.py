#
# Author: Claude Code
# Date: 2026-02-23
# Description: 知乎Dang报告渲染器 - 将JSON分析结果渲染为Markdown

import json
import re
from datetime import datetime
from typing import Dict, Any, List, Optional


class ZhihuDangReportRenderer:
    """
    知乎Dang报告渲染器
    将LLM返回的JSON格式分析结果渲染为结构化的Markdown报告
    """

    def __init__(self):
        pass

    def render(self, llm_output_json: str, source_url: str, published_at: Optional[datetime] = None) -> str:
        """
        渲染知乎分析报告的 Markdown

        Args:
            llm_output_json: LLM 返回的 JSON 字符串
            source_url: 原文链接
            published_at: 发布时间

        Returns:
            完整的 Markdown 字符串
        """
        # 1. 解析JSON（处理可能的Markdown代码块包裹）
        data = self._parse_json_from_llm(llm_output_json)

        # 2. 处理解析错误
        if "error_raw_text" in data:
            return self._render_error(data["error_raw_text"], source_url)

        # 3. 构建各个部分
        header = self._construct_header(data, source_url, published_at)
        recommendations = self._render_recommendations(data)  # 最重要，放最前
        coded_terms = self._render_coded_terms(data)
        logic_breakdown = self._render_logic_breakdown(data)
        methodology = self._render_methodology(data)
        uncertainties = self._render_uncertainties(data)

        return f"{header}\n\n{recommendations}\n\n{coded_terms}\n\n{logic_breakdown}\n\n{methodology}\n\n{uncertainties}"

    def _parse_json_from_llm(self, text: str) -> Dict[str, Any]:
        """清洗并解析 LLM 返回的 JSON"""
        if not text:
            return {}

        # 去除 Markdown 代码块标记
        cleaned_text = re.sub(r"^```json\s*", "", text.strip(), flags=re.MULTILINE)
        cleaned_text = re.sub(r"\s*```$", "", cleaned_text, flags=re.MULTILINE)

        try:
            return json.loads(cleaned_text)
        except json.JSONDecodeError:
            return {"error_raw_text": text}

    def _construct_header(self, data: Dict, source_url: str, published_at: Optional[datetime]) -> str:
        """构造文件头，包含元数据和原文链接"""
        meta = data.get("meta", {})
        title = meta.get("article_title", "MR Dang 文章深度解析")
        confidence = meta.get("confidence_level", "medium").capitalize()
        analysis_date = meta.get("analysis_date", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        header_lines = [
            "# 📊 MR Dang 文章深度解析",
            "",
            f"> 📅 **分析时间**: {analysis_date}",
            f"> 🔗 **原文链接**: [点击查看]({source_url})",
            f"> 📈 **置信度**: {confidence}",
            ""
        ]

        return "\n".join(header_lines)

    def _render_recommendations(self, data: Dict) -> str:
        """
        渲染操作建议部分 - 最重要的部分，放在最前面
        包含买入/卖出/持有信号，使用醒目的格式
        """
        recommendations = data.get("actionable_recommendations", {})
        buy_signals = recommendations.get("buy_signals", [])
        sell_signals = recommendations.get("sell_signals", [])
        hold_signals = recommendations.get("hold_signals", [])

        lines = [
            "## 🎯 操作建议 (Actionable Recommendations)",
            ""
        ]

        # 买入信号
        if buy_signals:
            lines.append("### 🟢 买入信号 (Buy Signals)")
            lines.append("")
            lines.append("| 股票代码 | 股票名称 | 置信度 | 目标价位 | 时间周期 |")
            lines.append("|---------|---------|--------|---------|---------|")

            for signal in buy_signals:
                stock_code = signal.get("stock_code", "N/A")
                stock_name = signal.get("stock_name", "N/A")
                confidence = signal.get("confidence", "medium").capitalize()
                price_target = signal.get("price_target", "待定")
                time_horizon = signal.get("time_horizon", "medium-term")

                # 翻译时间周期
                horizon_map = {
                    "short-term": "短期",
                    "medium-term": "中期",
                    "long-term": "长期"
                }
                horizon_cn = horizon_map.get(time_horizon, time_horizon)

                lines.append(f"| {stock_code} | {stock_name} | {confidence} | {price_target} | {horizon_cn} |")

            lines.append("")

            # 详细说明
            for signal in buy_signals:
                stock_code = signal.get("stock_code", "N/A")
                stock_name = signal.get("stock_name", "N/A")
                reasoning = signal.get("reasoning", "无")
                risk_factors = signal.get("risk_factors", [])

                lines.append(f"**{stock_code} - {stock_name}**")
                lines.append(f"- **买入逻辑**: {reasoning}")
                if risk_factors:
                    lines.append("- **风险因素**:")
                    for risk in risk_factors:
                        lines.append(f"  - {risk}")
                lines.append("")
        else:
            lines.append("### 🟢 买入信号 (Buy Signals)")
            lines.append("")
            lines.append("本文未提及明确的买入信号。")
            lines.append("")

        # 卖出信号
        if sell_signals:
            lines.append("### 🔴 卖出信号 (Sell Signals)")
            lines.append("")
            lines.append("| 股票代码 | 股票名称 | 置信度 |")
            lines.append("|---------|---------|--------|")

            for signal in sell_signals:
                stock_code = signal.get("stock_code", "N/A")
                stock_name = signal.get("stock_name", "N/A")
                confidence = signal.get("confidence", "medium").capitalize()
                lines.append(f"| {stock_code} | {stock_name} | {confidence} |")

            lines.append("")

            # 详细说明
            for signal in sell_signals:
                stock_code = signal.get("stock_code", "N/A")
                stock_name = signal.get("stock_name", "N/A")
                reasoning = signal.get("reasoning", "无")
                risk_factors = signal.get("risk_factors", [])

                lines.append(f"**{stock_code} - {stock_name}**")
                lines.append(f"- **卖出逻辑**: {reasoning}")
                if risk_factors:
                    lines.append("- **风险因素**:")
                    for risk in risk_factors:
                        lines.append(f"  - {risk}")
                lines.append("")
        else:
            lines.append("### 🔴 卖出信号 (Sell Signals)")
            lines.append("")
            lines.append("本文未提及明确的卖出信号。")
            lines.append("")

        # 持有观望
        if hold_signals:
            lines.append("### 🟡 持有观望 (Hold Signals)")
            lines.append("")

            for signal in hold_signals:
                stock_code = signal.get("stock_code", "N/A")
                stock_name = signal.get("stock_name", "N/A")
                reasoning = signal.get("reasoning", "无")

                lines.append(f"**{stock_code} - {stock_name}**")
                lines.append(f"- **持有理由**: {reasoning}")
                lines.append("")
        else:
            lines.append("### 🟡 持有观望 (Hold Signals)")
            lines.append("")
            lines.append("本文未提及明确的持有观望建议。")
            lines.append("")

        return "\n".join(lines)

    def _render_coded_terms(self, data: Dict) -> str:
        """渲染暗语翻译表"""
        coded_terms = data.get("coded_terms_translation", [])

        if not coded_terms:
            return "## 🔤 暗语翻译表 (Coded Terms Translation)\n\n无暗语翻译内容。"

        lines = [
            "## 🔤 暗语翻译表 (Coded Terms Translation)",
            ""
        ]

        for term in coded_terms:
            original = term.get("original_term", "N/A")
            stock_name = term.get("stock_name", "N/A")
            stock_code = term.get("stock_code", "N/A")
            certainty = term.get("certainty", "speculated")
            reasoning = term.get("reasoning", "")

            certainty_cn = "确定" if certainty == "confirmed" else "推测"
            lines.append(f"- **{original}** → {stock_name} ({stock_code}) | 确定性：{certainty_cn} | 依据：{reasoning}")

        return "\n".join(lines)

    def _render_logic_breakdown(self, data: Dict) -> str:
        """渲染文章逻辑梳理"""
        logic_breakdown = data.get("article_logic_breakdown", [])

        if not logic_breakdown:
            return "## 📖 文章逻辑梳理 (Article Logic Breakdown)\n\n无文章逻辑梳理内容。"

        lines = [
            "## 📖 文章逻辑梳理 (Article Logic Breakdown)",
            ""
        ]

        for section in logic_breakdown:
            section_num = section.get("section_number", 0)
            original_text = section.get("original_text", "")
            interpretation = section.get("interpretation", "")
            key_points = section.get("key_points", [])
            mentioned_stocks = section.get("mentioned_stocks", [])

            lines.append(f"### 段落 {section_num}")
            lines.append("")
            lines.append(f"**原文**：{original_text}")
            lines.append("")
            lines.append(f"**解读**：{interpretation}")
            lines.append("")

            if key_points:
                lines.append("**要点**：")
                for point in key_points:
                    lines.append(f"- {point}")
                lines.append("")

            if mentioned_stocks:
                lines.append(f"**提及标的**：{', '.join(mentioned_stocks)}")
                lines.append("")

        return "\n".join(lines)

    def _render_methodology(self, data: Dict) -> str:
        """渲染方法论总结"""
        methodology = data.get("methodology_summary", {})

        if not methodology:
            return "## 🧠 方法论总结 (Methodology Summary)\n\n无方法论总结内容。"

        lines = [
            "## 🧠 方法论总结 (Methodology Summary)",
            ""
        ]

        stock_selection = methodology.get("stock_selection_logic", [])
        if stock_selection:
            lines.append("### 选股逻辑")
            for logic in stock_selection:
                lines.append(f"- {logic}")
            lines.append("")

        timing_strategy = methodology.get("timing_strategy", "")
        if timing_strategy:
            lines.append("### 择时策略")
            lines.append(f"{timing_strategy}")
            lines.append("")

        risk_management = methodology.get("risk_management", "")
        if risk_management:
            lines.append("### 风控原则")
            lines.append(f"{risk_management}")
            lines.append("")

        market_view = methodology.get("market_view", "")
        if market_view:
            lines.append("### 市场观点")
            lines.append(f"{market_view}")
            lines.append("")

        return "\n".join(lines)

    def _render_uncertainties(self, data: Dict) -> str:
        """渲染不确定项"""
        uncertainties = data.get("uncertainties", [])

        if not uncertainties:
            return "## ⚠️ 不确定项 (Uncertainties)\n\n无不确定项。"

        lines = [
            "## ⚠️ 不确定项 (Uncertainties)",
            ""
        ]

        for uncertainty in uncertainties:
            item = uncertainty.get("item", "")
            impact = uncertainty.get("impact", "")
            verification_needed = uncertainty.get("verification_needed", "")

            lines.append(f"### {item}")
            if impact:
                lines.append(f"- **可能影响**：{impact}")
            if verification_needed:
                lines.append(f"- **需要验证**：{verification_needed}")
            lines.append("")

        return "\n".join(lines)

    def _render_error(self, raw_text: str, source_url: str) -> str:
        """渲染解析失败的情况"""
        lines = [
            "# 📊 MR Dang 文章深度解析",
            "",
            f"> 🔗 **原文链接**: [点击查看]({source_url})",
            "",
            "---",
            "",
            "> ⚠️ **JSON格式解析失败，以下为原始输出：**",
            "",
            "```",
            raw_text,
            "```"
        ]

        return "\n".join(lines)
