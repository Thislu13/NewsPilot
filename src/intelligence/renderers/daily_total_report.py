from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import re

class DailyTotalReportRenderer:
    def render(self, llm_output_json: str, date: datetime.date) -> str:
        """
        渲染 Total 版本的 Markdown (纯情报版，不附带原始新闻链接列表)
        """
        data = self._parse_json(llm_output_json)
        if "error_raw_text" in data:
            return f"> ⚠️ 格式解析失败，原始输出：\n\n{data['error_raw_text']}"

        lines = []
        
        # --- Header Optimization ---
        lines.append(f"# 🌍 全球全领域深度日报 (Total Daily Report)")
        lines.append(f"")
        lines.append(f"> 📅 **日期**: {date.strftime('%Y-%m-%d')}")
        lines.append(f"> 🚀 **生成引擎**: [**NewsPilot**](https://github.com/Thislu13/NewsPilot)")
        lines.append(f"> ✨ *开源的自动化情报分析系统*")
        lines.append(f"")
        
        meta = data.get("meta", {})
        insight = meta.get("cross_domain_insight", "")
        if insight:
            lines.append(f"### 🔍 今日宏观洞察")
            lines.append(f"> {insight}")
            lines.append("")
        
        lines.append("---")
        lines.append("")

        # 1. Top Stories
        top_stories = data.get("top_stories", [])
        if top_stories:
            lines.append("## 🚨 今日头条 (Top Stories)")
            for i, story in enumerate(top_stories, 1):
                title = story.get("title", "未命名事件")
                summary = story.get("summary", "")
                domains = story.get("impact_domains", [])
                key_data = story.get("key_data", [])
                strategy = story.get("strategic_insight", "")
                
                lines.append(f"### {i}. {title}")
                if domains:
                     dom_str = " ".join([f"`{d}`" for d in domains])
                     lines.append(f"- **🏷️ 涉及领域**: {dom_str}")
                
                lines.append(f"{summary}")
                lines.append("")
                
                if key_data:
                    lines.append(f"- **📊 关键数据**: {'; '.join(key_data)}")
                
                if strategy:
                    lines.append(f"- **🧠 战略研判**: {strategy}")
                
                lines.append("")

        # 2. Category Deep Dive
        # 这里是重点：高密度情报，但不带原始新闻列表 (因为太长且不属于 high-level insight)
        deep_dives = data.get("category_deep_dive", [])
        if deep_dives:
            lines.append("## 📂 分领域精编情报")
            for cat in deep_dives:
                name = cat.get("category_name", "未知领域")
                signal = cat.get("trend_signal", "")
                highlights = cat.get("highlights", [])
                
                lines.append(f"### 🔹 {name}")
                if signal:
                    lines.append(f"> **🌊 趋势信号**: {signal}")
                    lines.append("")
                
                for hl in highlights:
                    topic = hl.get("topic", "")
                    detail = hl.get("detail", "")
                    lines.append(f"- **{topic}**: {detail}")
                lines.append("")

        # 3. Global Industry Scan (New Section)
        # 整合约 20-50 条各领域简报
        industry_scan = data.get("global_industry_scan", [])
        if industry_scan:
            lines.append("## 🌐 今日全球新闻看点 (Industry Scan)")
            for sector in industry_scan:
                domain_name = sector.get("domain", "其他")
                items = sector.get("items", [])
                if items:
                    lines.append(f"### 📍 {domain_name}")
                    for item in items:
                        lines.append(f"- {item}")
                    lines.append("")

        # 4. Risk Radar
        risks = data.get("risk_radar", [])
        if risks:
             lines.append("## 🛡️ 全局风险雷达")
             lines.append("")
             lines.append("| ⚠️ 风险类型 | 📝 描述 | 🔥 严重程度 |")
             lines.append("| :--- | :--- | :--- |")
             for r in risks:
                 rtype = r.get("risk_type", "-")
                 desc = r.get("description", "-")
                 severity = r.get("severity", "-")
                 lines.append(f"| {rtype} | {desc} | {severity} |")
             lines.append("")

        # 5. Global Investment & Arbitrage Map
        inv_map = data.get("investment_arbitrage_map", [])
        if inv_map:
            lines.append("## 💎 全局套利与红利地图")
            lines.append("")
            
            for item in inv_map:
                logic = item.get("logic_chain", "")
                sectors = item.get("sector_focus", [])
                insight = item.get("actionable_insight", "")
                
                lines.append(f"### 🔗 逻辑链: {logic}")
                if sectors:
                     sec_str = "、".join([f"`{s}`" for s in sectors])
                     lines.append(f"- **🎯 关注板块**: {sec_str}")
                lines.append(f"- **💡 投资建议**: {insight}")
                lines.append("")

        # --- Footer ---
        lines.append("---")
        lines.append("### ℹ️ 关于本报告")
        lines.append(f"本报告由开源项目 **[NewsPilot](https://github.com/Thislu13/NewsPilot)** 自动生成。")
        lines.append(f"NewsPilot 是一个**开源的自动化情报分析系统**，利用 LLM 技术对多源新闻进行聚合、筛选、摘要与深度分析。")
        lines.append("欢迎 Star ⭐ 关注项目发展。")

        return "\n".join(lines)

    def _parse_json(self, text: str) -> Dict[str, Any]:
        if not text: return {}
        cleaned = re.sub(r"^```json\s*", "", text.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
        try:
            return json.loads(cleaned)
        except:
             return {"error_raw_text": text}
