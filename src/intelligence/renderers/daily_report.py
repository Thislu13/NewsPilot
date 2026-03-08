import json
import re
from datetime import datetime
from typing import Dict, Any, List, Optional

class DailyReportRenderer:
    def __init__(self, category_map: Optional[Dict[str, str]] = None):
        self.category_map = category_map or {}

    def render(self, category: str, llm_output_json: str, date: datetime.date, news_items: Optional[List[Any]] = None) -> str:
        """
        渲染完整的日报 Markdown (含标题、元数据、解析后的内容、新闻列表附录)
        :param category: 分类 Key (如 policy_regulation)
        :param llm_output_json: LLM 返回的原始 JSON 字符串
        :param date: 报告日期
        :param news_items: 原始精炼新闻列表 (RefinedNews list)
        :return: 完整的 Markdown 字符串
        """
        # 1. 尝试解析 JSON
        data = self._parse_json_from_llm(llm_output_json)
        
        # 如果解析失败，返回包含错误提示的原始文本
        if "error_raw_text" in data:
            header = self._construct_header(category, date)
            error_msg = f"> ⚠️ 格式解析失败，以下为原始输出：\n\n{data['error_raw_text']}"
            return f"{header}\n{error_msg}"

        # 2. 生成 Header
        header = self._construct_header(category, date)

        # 3. 生成 Body
        body = self._render_body(data)

        # 4. 生成 News Appendix
        appendix = self._render_news_appendix(news_items)

        return f"{header}\n{body}\n\n{appendix}"

    def _render_news_appendix(self, news_items: Optional[List[Any]]) -> str:
        """生成新闻列表附录"""
        if not news_items:
            return ""

        lines = [
            "## 🗃️ 原始新闻资料",
            ""
        ]

        # 按时间倒序
        try:
            sorted_items = sorted(news_items, key=lambda x: x.published_at, reverse=True)
        except Exception:
            sorted_items = news_items

        for i, item in enumerate(sorted_items, 1):
            try:
                # 准备数据
                title = getattr(item, 'title', '无标题') or "无标题"
                title = title.replace('\n', ' ').strip()
                
                url = getattr(item, 'source_url', '') or ''
                source = getattr(item, 'source_channel', 'Unknown')
                
                if hasattr(item.published_at, 'strftime'):
                    pub_str = item.published_at.strftime('%Y-%m-%d %H:%M')
                else:
                    pub_str = str(item.published_at)

                abstract = getattr(item, 'abstract', '') or "暂无摘要"
                abstract = abstract.replace('\n', ' ').strip()
                
                # 渲染格式
                # 1. 标题行：序号. [标题](URL)
                
                title_line = f"**{i}. [{title}]({url})**" if url else f"**{i}. {title}**"
                
                lines.append(title_line)
                lines.append(f"- **来源**： {source} &nbsp;&nbsp; **时间**： {pub_str}")
                lines.append(f"- **摘要**： {abstract}")
                lines.append("")
                
            except Exception:
                continue
        
        return "\n".join(lines)

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

    def _construct_header(self, category: str, date: datetime.date) -> str:
        """构造文件头"""
        cn_name = self.category_map.get(category, category)
        
        lines = [
            f"# 📅 {cn_name} 行业深度日报",
            "",
            f"> 🕒 **日期**: {date.strftime('%Y-%m-%d')}",
            "> 🚀 **生成引擎**: [**NewsPilot**](https://github.com/Thislu13/NewsPilot)",
            "> ✨ *开源的自动化情报分析系统*",
            ""
        ]
        return "\n".join(lines)

    def _render_body(self, data: Dict[str, Any]) -> str:
        """根据 JSON 数据渲染正文内容"""
        md_lines = []
        meta = data.get("meta", {})
        
        # 头部概览
        md_lines.append("")
        md_lines.append(f"> 📊 **情报综述** | 覆盖新闻数: {meta.get('news_coverage_count', 'N/A')} | 生成时间: {datetime.now().strftime('%H:%M')}")
        md_lines.append("")
        
        # 每日综述 (Overall Commentary)
        overall = data.get("overall_commentary", "")
        if overall:
            md_lines.append("## 📝 重点综述")
            md_lines.append(f"{overall}\n")
            md_lines.append("---")

        # A. 核心情报 (Core Events)
        core_events = data.get("core_events", [])
        if core_events:
            md_lines.append("## 🔥 核心情报")
            for i, event in enumerate(core_events, 1):
                self._render_single_event(md_lines, i, event)
                md_lines.append("---")
        
        # B. 行业扫描 (Industry Scan)
        industry_scan = data.get("industry_scan", [])
        if industry_scan:
            md_lines.append("## 📰 行业扫描")
            for item in industry_scan:
                sub_topic = item.get("sub_topic", "通用")
                briefs = item.get("briefs", [])
                
                md_lines.append(f"**🔹 {sub_topic}**")
                if isinstance(briefs, list):
                    for brief in briefs:
                        md_lines.append(f"- {brief}")
                else:
                    md_lines.append(f"- {briefs}")
                md_lines.append("")
        
        # C. 市场监测 (Market Monitor)
        monitor = data.get("market_monitor", {})
        if monitor:
            md_lines.append("## 📉 市场监测")
            observed = monitor.get("observed_changes", "未录得显著波动")
            signal = monitor.get("trend_signal", "观望")
            
            md_lines.append(f"- **市场变动**: {observed}")
            md_lines.append(f"- **系统信号**: `{signal}`")
            md_lines.append("")

        return "\n".join(md_lines)

    def _render_single_event(self, md_lines: List[str], index: int, event: Dict[str, Any]):
        """渲染单个事件"""
        title = event.get("title", "未命名情报")
        facts = event.get("facts", {})
        what_happened = facts.get("what_happened", "")
        data_points = facts.get("data_points", [])
        reactions = event.get("reactions", "未观察到显著反应")
        sources = event.get("sources", [])
        
        # 标题
        md_lines.append(f"### {index}. {title}")
        
        # 事实层
        md_lines.append(f"{what_happened}")
        if data_points:
            points_str = "、".join([f"`{dp}`" for dp in data_points])
            md_lines.append(f"*   **关键数据**: {points_str}")
        
        # 来源标注
        if sources:
            md_lines.append(f"*   <small style='color:grey'>来源: {', '.join(sources)}</small>")

        # 反应层
        md_lines.append("")
        if reactions and reactions != "未观察到显著反应":
                md_lines.append(f"> 📢 **各方反应**: {reactions}")
        
        # 研判层 (专家模型研判)
        outlook = event.get("expert_outlook", {})
        sys_analysis = event.get("system_analysis", "") # 兼容旧字段
        
        if outlook or sys_analysis:
                md_lines.append(f"> 🧠 **专家模型研判**")
                
                if sys_analysis: # Fallback for old data
                    md_lines.append(f"> *   **分析**: {sys_analysis}")
                
                if outlook:
                    eval_text = outlook.get("evaluation", "")
                    pred_text = outlook.get("prediction", "")
                    counter_text = outlook.get("counterfactual_analysis", "")
                    
                    if eval_text:
                        md_lines.append(f"> *   **评价**: {eval_text}")
                    if pred_text:
                        md_lines.append(f"> *   **预测**: {pred_text}")
                    if counter_text:
                        md_lines.append(f"> *   **反向推演**: {counter_text}")
