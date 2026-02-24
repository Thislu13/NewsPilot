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

        # 3. 构建各个部分（按照用户期望的结构）
        header = self._construct_header(data, source_url, published_at)
        recommendations = self._render_recommendations(data)  # 操作建议（最前）
        coded_terms = self._render_coded_terms(data)  # 暗语对照
        content_analysis = self._render_content_analysis(data)  # 详细内容解析
        arbitrage_logic = self._render_arbitrage_logic(data)  # 套利逻辑
        article_summary = self._render_article_summary(data)  # 文章总结
        methodology = self._render_methodology(data)  # 整体策略
        uncertainties = self._render_uncertainties(data)

        parts = [header]
        if recommendations:
            parts.append(recommendations)
        if coded_terms:
            parts.append(coded_terms)
        if content_analysis:
            parts.append(content_analysis)
        if arbitrage_logic:
            parts.append(arbitrage_logic)
        if article_summary:
            parts.append(article_summary)
        if methodology:
            parts.append(methodology)
        if uncertainties:
            parts.append(uncertainties)

        # 添加免责声明（始终显示）
        disclaimer = self._render_disclaimer()
        parts.append(disclaimer)

        return "\n\n".join(parts)

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

    def _render_coded_terms(self, data: Dict) -> str:
        """渲染暗语翻译表"""
        coded_terms = data.get("coded_terms_translation", [])

        if not coded_terms:
            return ""

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

    def _render_content_analysis(self, data: Dict) -> str:
        """渲染详细内容解析（分点详细解析，包含专业术语解读）"""
        content_analysis = data.get("detailed_content_analysis", [])

        if not content_analysis:
            return ""

        lines = [
            "## 📖 详细内容解析 (Detailed Content Analysis)",
            ""
        ]

        for idx, section in enumerate(content_analysis, 1):
            topic_title = section.get("topic_title", f"主题 {idx}")
            analysis = section.get("analysis", "")
            key_terminology = section.get("key_terminology", [])
            key_points = section.get("key_points", [])
            mentioned_stocks = section.get("mentioned_stocks", [])

            lines.append(f"### {idx}. {topic_title}")
            lines.append("")

            if analysis:
                lines.append(f"**详细解析**：")
                lines.append(analysis)
                lines.append("")

            if key_terminology:
                lines.append("**📌 专业术语解读**：")
                for term_info in key_terminology:
                    term = term_info.get("term", "")
                    explanation = term_info.get("explanation", "")
                    relevance = term_info.get("relevance", "")
                    if term and explanation:
                        lines.append(f"- **{term}**：{explanation}")
                        if relevance:
                            lines.append(f"  - 作用：{relevance}")
                lines.append("")

            if key_points:
                lines.append("**💡 核心要点**：")
                for point in key_points:
                    lines.append(f"- {point}")
                lines.append("")

            if mentioned_stocks:
                lines.append(f"**📈 相关标的**：{', '.join(mentioned_stocks)}")
                lines.append("")

            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    def _render_recommendations(self, data: Dict) -> str:
        """
        渲染操作建议部分
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

    def _render_arbitrage_logic(self, data: Dict) -> str:
        """渲染套利逻辑分析"""
        arbitrage_logic = data.get("arbitrage_logic", [])

        if not arbitrage_logic:
            return ""

        lines = [
            "## 💰 潜在套利逻辑 (Arbitrage Opportunities)",
            ""
        ]

        for idx, opportunity in enumerate(arbitrage_logic, 1):
            logic_chain = opportunity.get("logic_chain", "")
            description = opportunity.get("opportunity_description", "")
            operation_direction = opportunity.get("operation_direction", "")
            beneficiary_sectors = opportunity.get("beneficiary_sectors", [])
            beneficiary_stocks = opportunity.get("beneficiary_stocks", [])
            entry_timing = opportunity.get("entry_timing", "")
            risk_factors = opportunity.get("risk_factors", [])
            expected_return = opportunity.get("expected_return", "")

            lines.append(f"### 机会 {idx}")
            lines.append("")

            if logic_chain:
                lines.append(f"**🔍 逻辑链路**：{logic_chain}")
                lines.append("")

            if description:
                lines.append(f"**📝 机会描述**：")
                lines.append(description)
                lines.append("")

            if operation_direction:
                lines.append(f"**➡️ 操作方向**：{operation_direction}")
                lines.append("")

            if beneficiary_sectors:
                lines.append(f"**🏭 受益板块**：{', '.join(beneficiary_sectors)}")
                lines.append("")

            if beneficiary_stocks:
                lines.append(f"**📈 受益标的**：{', '.join(beneficiary_stocks)}")
                lines.append("")

            if entry_timing:
                lines.append(f"**⏰ 入场时机**：{entry_timing}")
                lines.append("")

            if risk_factors:
                lines.append(f"**⚠️ 风险因素**：")
                for risk in risk_factors:
                    lines.append(f"- {risk}")
                lines.append("")

            if expected_return:
                lines.append(f"**🎯 预期收益**：{expected_return}")
                lines.append("")

            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    def _render_article_summary(self, data: Dict) -> str:
        """渲染文章总结"""
        article_summary = data.get("article_summary", {})

        if not article_summary:
            return ""

        lines = [
            "## 📌 文章总结 (Article Summary)",
            ""
        ]

        # 核心观点
        core_viewpoint = article_summary.get("core_viewpoint", "")
        if core_viewpoint:
            lines.append("### 🎯 核心观点")
            lines.append("")
            lines.append(core_viewpoint)
            lines.append("")

        # 关键发现
        key_findings = article_summary.get("key_findings", [])
        if key_findings:
            lines.append("### 💡 关键发现")
            lines.append("")
            for idx, finding in enumerate(key_findings, 1):
                lines.append(f"{idx}. {finding}")
            lines.append("")

        # 市场展望
        market_outlook = article_summary.get("market_outlook", {})
        if market_outlook:
            lines.append("### 🔮 市场展望")
            lines.append("")

            short_term = market_outlook.get("short_term", "")
            if short_term:
                lines.append(f"**短期（1-2周）**：{short_term}")
                lines.append("")

            medium_term = market_outlook.get("medium_term", "")
            if medium_term:
                lines.append(f"**中期（1-3个月）**：{medium_term}")
                lines.append("")

        return "\n".join(lines)

    def _render_methodology(self, data: Dict) -> str:
        """渲染方法论总结"""
        methodology = data.get("methodology_summary", {})

        if not methodology:
            return ""

        lines = [
            "## 🧠 整体策略 (Overall Strategy)",
            ""
        ]

        stock_selection = methodology.get("stock_selection_logic", [])
        if stock_selection:
            lines.append("### 1. 选股逻辑")
            for logic in stock_selection:
                lines.append(f"- {logic}")
            lines.append("")

        timing_strategy = methodology.get("timing_strategy", "")
        if timing_strategy:
            lines.append("### 2. 择时策略")
            lines.append(f"{timing_strategy}")
            lines.append("")

        risk_management = methodology.get("risk_management", "")
        if risk_management:
            lines.append("### 3. 风控原则")
            lines.append(f"{risk_management}")
            lines.append("")

        market_view = methodology.get("market_view", "")
        if market_view:
            lines.append("### 4. 市场观点")
            lines.append(f"{market_view}")
            lines.append("")

        return "\n".join(lines)

    def _render_uncertainties(self, data: Dict) -> str:
        """渲染不确定项"""
        uncertainties = data.get("uncertainties", [])

        if not uncertainties:
            return ""

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

    def _render_disclaimer(self) -> str:
        """渲染投资风险提示与免责声明"""
        lines = [
            "---",
            "",
            "## ⚠️ 投资风险提示与免责声明",
            "",
            "### 📢 重要声明",
            "",
            "本报告由 AI 系统自动生成，旨在对自媒体财经内容进行结构化分析和信息提取。报告内容仅供参考，**不构成任何投资建议**。",
            "",
            "### 🚨 风险提示",
            "",
            "1. **信息来源风险**",
            "   - 本报告分析的原文来自自媒体博主，其观点可能存在主观性、片面性或时效性问题",
            "   - 原文中的\"暗语\"映射可能存在误判，请务必独立核实",
            "",
            "2. **市场风险**",
            "   - 股票市场存在系统性风险，股价波动受多种因素影响",
            "   - 历史表现不代表未来收益，任何投资策略都可能面临亏损",
            "   - 市场环境变化可能导致分析结论失效",
            "",
            "3. **操作风险**",
            "   - 本报告提及的\"买入\"、\"卖出\"等操作建议均基于原文内容提取，不代表本系统推荐",
            "   - 投资决策应基于您自身的风险承受能力、财务状况和投资目标",
            "   - 建议咨询专业投资顾问后再做决策",
            "",
            "4. **技术风险**",
            "   - AI 分析可能存在理解偏差、信息遗漏或逻辑错误",
            "   - 专业术语解读仅供参考，不保证完全准确",
            "",
            "### 📋 免责条款",
            "",
            "- 本报告**不构成**证券投资咨询服务",
            "- 使用本报告信息进行投资决策所产生的一切后果，由投资者自行承担",
            "- 本系统及其运营方对因使用本报告而导致的任何直接或间接损失不承担责任",
            "- 投资者应独立判断并自行承担投资风险",
            "",
            "### ✅ 合规建议",
            "",
            "- 请通过正规渠道获取上市公司信息（如交易所公告、财报等）",
            "- 建议参考多方信息源，进行交叉验证",
            "- 理性投资，审慎决策，切勿盲目跟风",
            "",
            "---",
            "",
            "*本报告生成时间以文件元数据为准。市场有风险，投资需谨慎。*"
        ]

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
