# src/intelligence/new_analyzer.py
"""
新闻分析引擎 - 不管理用户画像，只专注分析
职责：
1. (Function A) 入口：协调获取新闻、分类、调用生成、保存文件
2. (Function B) 生成：针对单分类准备 Prompt 并调用 LLM
3. LLM 适配：兼容 OpenAI 格式 (DeepSeek, GPT, Qwen) 和 Gemini
"""

import os
import asyncio
import json
import re
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from google import genai
from google.genai import types
from google.genai.types import GenerateContentConfig, ThinkingConfig, Tool

from core.news_schemas import NewsItemRefinedSchema
from src.module.init_client import LLMClientFactory
from config.prompts import CATEGORY_DAILY_REPORT_PROMPT, TOTAL_DAILY_REPORT_PROMPT
from src.storage.repository import StorageRepository
from src.storage.models import RefinedNews
from src.intelligence.renderers import DailyReportRenderer, DailyTotalReportRenderer
from src.module.content_converter import ContentConverter

class NewsAnalyzer:
    def __init__(self, model_name: str = "gemini"):
        self.factory = LLMClientFactory()
        self.repo = StorageRepository()
        self.model_name = model_name
        self.client = self.factory.get_client(model_name)
        
        self.category_map = {
            "policy_regulation": "政策与法规",
            "macro_economy": "宏观经济",
            "markets": "金融市场",
            "company_business": "公司与商业",
            "technology": "科技前沿",
            "energy_commodities": "能源与大宗商品",
            "geopolitics": "地缘政治",
            "society_public_safety": "社会与公共安全",
            "environment_climate": "环境与气候",
            "health_medicine": "医疗健康"
        }
        self.renderer = DailyReportRenderer(self.category_map)
        self.total_renderer = DailyTotalReportRenderer()
        self.converter = ContentConverter()

    async def generate_all_daily_reports(
        self, 
        target_date: Optional[datetime.date] = None, 
        time_range: Optional[tuple[datetime, datetime]] = None,
        # 新增细粒度控制参数
        save_md_list: Optional[List[str]] = "ALL",      # None=不保存, "ALL"=全保存
        save_html_list: Optional[List[str]] = ["total"],    # None=不保存, "ALL"=全保存
        save_pdf_list: Optional[List[str]] = "ALL_CATEGORIES",     # None=不保存, "ALL"=全保存
        md_output_dir: Optional[str] = None,
        html_output_dir: Optional[str] = None,
        pdf_output_dir: Optional[str] = None
    ) -> Dict[str, Dict[str, str]]:
        """
        核心入口 (V2 重构版)
        :param target_date: 报告归属日期
        :param time_range: (start, end) 时间范围，与 target_date 互斥
        :param save_md_list: 需要保存 MD 的分类列表 (如 ["policy_regulation", "total"])
        :param save_html_list: 需要保存 HTML 的分类列表
        :param save_pdf_list: 需要保存 PDF 的分类列表
        """
        # 0. 参数归一化与默认值处理
        if not target_date and not time_range:
             target_date = datetime.now().date()
        
        display_date = target_date if target_date else time_range[1].date()
        
        # 兼容旧逻辑：如果只传了 save_path，则将其作为所有格式的默认根目录，且默认开启 MD Output
        base_dir = os.getcwd()
        if md_output_dir is None: md_output_dir = base_dir
        if html_output_dir is None: html_output_dir = base_dir
        if pdf_output_dir is None: pdf_output_dir = base_dir
        
        print(f"[*] 开始生成 {display_date} 日报，使用模型: {self.model_name}")
        
        # 1. 准备数据
        news_items = self._fetch_news(target_date, time_range)
        if not news_items:
            print(f"[!] {display_date} (范围: {time_range}) 无新闻数据")
            return {}
            
        categorized_news = self._classify_news(news_items)
        valid_categories = [k for k,v in categorized_news.items() if v]
        print(f"[*] 新闻分类完成，覆盖 {len(valid_categories)} 个领域")
        
        results = {}
        tasks = []
        
        # 2. 并行生成各分领域报告 (必须步骤，无论是否保存)
        for category, items in categorized_news.items():
            if not items:
                continue
            task = self._generate_single_category_content(category, items, display_date)
            tasks.append((category, task))
            
        if not tasks:
            return {}
            
        cat_keys = [t[0] for t in tasks]
        awaitables = [t[1] for t in tasks]
        
        print(f"[*] Step 1: 调用 LLM 生成 {len(tasks)} 个分领域报告...")
        analysis_contents = await asyncio.gather(*awaitables)
        
        # 存储分领域的原始 JSON，供 Total 生成使用
        domain_json_map = {} 

        # 3. 处理分领域结果 & 文件保存
        for category, raw_json in zip(cat_keys, analysis_contents):
            domain_json_map[category] = raw_json
            
            # 渲染 MD
            news_list_for_appendix = categorized_news.get(category, [])
            md_content = self.renderer.render(category, raw_json, display_date, news_list_for_appendix)
            
            # 生成 HTML
            html_content = self.converter.md_to_html(md_content, full_page=True)

            # 保存逻辑
            saved_paths = await self._handle_file_saving(
                category=category,
                display_date=display_date,
                md_content=md_content,
                html_content=html_content,
                save_md_list=save_md_list,
                save_html_list=save_html_list,
                save_pdf_list=save_pdf_list,
                md_dir=md_output_dir,
                html_dir=html_output_dir,
                pdf_dir=pdf_output_dir
            )

            results[category] = {
                "llm_output": raw_json,
                "md_content": md_content,
                **saved_paths
            }

        # 4. 生成 Total 汇总日报 (Step 2)
        print(f"[*] Step 2: 正在生成 Total 汇总日报 (基于 {len(domain_json_map)} 个分报告)...")
        total_raw_json = await self._generate_total_report(domain_json_map, display_date)
        
        # 渲染 Total MD (不带新闻附录)
        total_md = self.total_renderer.render(total_raw_json, display_date)
        
        # 准备打赏码路径 (仅在 Total 报告中添加)
        pay_img_path = os.path.join(os.path.dirname(__file__), 'renderers', 'pay.png')
        
        total_html = self.converter.md_to_html(
            total_md, 
            full_page=True, 
            footer_image_path=pay_img_path
        )
        
        # 保存 Total
        total_paths = await self._handle_file_saving(
            category="total",
            display_date=display_date,
            md_content=total_md,
            html_content=total_html,
            save_md_list=save_md_list,
            save_html_list=save_html_list,
            save_pdf_list=save_pdf_list,
            md_dir=md_output_dir,
            html_dir=html_output_dir,
            pdf_dir=pdf_output_dir
        )
        
        results["total"] = {
            "llm_output": total_raw_json,
            "md_content": total_md,
            **total_paths
        }
                
        print(f"[*] 所有报告生成完毕。")
        return results

    async def _handle_file_saving(
        self, category, display_date, md_content, html_content,
        save_md_list, save_html_list, save_pdf_list,
        md_dir, html_dir, pdf_dir
    ) -> Dict[str, str]:
        """统一文件保存处理逻辑"""
        paths = {}
        
        # 获取中文文件名 用于文件命名
        cn_name = self.category_map.get(category, category)
        if category == "total":
             cn_name = "0_全领域深度日报_汇总" # 加个前缀让它排第一
            
        # MD
        if self._should_save(category, save_md_list):
            path = self._build_path(md_dir, display_date, f"{cn_name}.md")
            self._write_text(path, md_content)
            paths["md_path"] = path

        # HTML
        if self._should_save(category, save_html_list):
            path = self._build_path(html_dir, display_date, f"{cn_name}.html")
            self._write_text(path, html_content)
            paths["html_path"] = path

        # PDF
        if self._should_save(category, save_pdf_list):
            path = self._build_path(pdf_dir, display_date, f"{cn_name}.pdf")
            await self.converter.save_pdf(md_content, path)
            paths["pdf_path"] = path
            
        return paths

    def _should_save(self, category: str, rule: Any) -> bool:
        if not rule: return False
        if rule == "ALL": return True
        if rule == "ALL_CATEGORIES" and category != "total": return True
        if isinstance(rule, list) and (category in rule or "ALL" in rule): return True
        return False

    def _build_path(self, root: str, date: datetime.date, filename: str) -> str:
        # 如果路径中包含 'test' (不区分大小写)，则视为测试目录，不自动创建日期子文件夹
        if 'test' in root.lower().split(os.sep): 
             full_folder = root
        else:
            # 默认保持 YYYY-MM-DD 子目录结构
            date_folder = date.strftime("%Y-%m-%d")
            full_folder = os.path.join(root, date_folder)
            
        os.makedirs(full_folder, exist_ok=True)
        return os.path.join(full_folder, filename)

    def _write_text(self, path: str, text: str):
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"   [+] Saved: {path}")
        except Exception as e:
            print(f"   [!] Failed to save {path}: {e}")

    async def _generate_total_report(self, domain_json_map: Dict[str, str], date: datetime.date) -> str:
        """生成 Total 汇总报告"""
        # 拼接 JSON 素材
        combined_json_str = ""
        for cat, json_str in domain_json_map.items():
            cn_cat = self.category_map.get(cat, cat)
            combined_json_str += f"\n=== {cn_cat} ===\n{json_str}\n"

        system_prompt = TOTAL_DAILY_REPORT_PROMPT["SYSTEM_PROMPT"]
        user_prompt = TOTAL_DAILY_REPORT_PROMPT["USER_PROMPT_TEMPLATE"].format(
            date=date.strftime("%Y-%m-%d"),
            domain_reports_json=combined_json_str
        )
        
        # 复用 _call_llm 进行调用 (只试一次，失败不重试或简单重试)
        try:
            return await self._call_llm(system_prompt, user_prompt)
        except Exception as e:
            return json.dumps({"error": str(e), "meta": {}})

    # ... _fetch_news 和 _classify_news 保持不变 ...
    def _fetch_news(self, target_date: Optional[datetime.date], time_range: Optional[tuple[datetime, datetime]] = None) -> List[RefinedNews]:
        """辅助：从数据库拉取 RefinedNews"""
        if time_range:
            date_from, date_to = time_range
        elif target_date:
            date_from = datetime.combine(target_date, datetime.min.time())
            date_to = datetime.combine(target_date, datetime.max.time())
        else:
             return []

        print(f"   [-] Fetching news from {date_from} to {date_to}")
        return self.repo.list_refined_news(
            date_from=date_from, 
            date_to=date_to, 
            date_field="published_at"
        )

    def _classify_news(self, news_items: List[RefinedNews]) -> Dict[str, List[RefinedNews]]:
        """辅助：按 Label 分类"""
        categorized = {cat: [] for cat in self.category_map.keys()}
        for news in news_items:
            if not news.categories:
                continue
            tags = news.categories if isinstance(news.categories, list) else []
            for tag in tags:
                if tag in categorized:
                    categorized[tag].append(news)
        return categorized

    async def _generate_single_category_content(
        self, 
        category: str, 
        news_items: List[RefinedNews], 
        date: datetime.date
    ) -> str:
        """
        单个领域的分析逻辑
        """
        # 1. 提取指令
        instruction = CATEGORY_DAILY_REPORT_PROMPT["CATEGORY_INSTRUCTIONS"].get(category, "综合分析行业动态。")
        
        # 2. 格式化新闻
        news_text_list = []
        for item in news_items:
            time_str = item.published_at.strftime('%H:%M')
            abstract = item.abstract[:150] + "..." if item.abstract and len(item.abstract) > 150 else item.abstract
            news_text_list.append(f"- [{time_str}] {item.title}: {abstract}")
        news_text = "\n".join(news_text_list)
        
        # 3. 填充 Prompt
        system_prompt = CATEGORY_DAILY_REPORT_PROMPT["SYSTEM_PROMPT"].format(
            category=self.category_map.get(category, category),
            instruction=instruction
        )
        
        user_prompt = CATEGORY_DAILY_REPORT_PROMPT["USER_PROMPT_TEMPLATE"].format(
            date=date.strftime("%Y-%m-%d"),
            category=self.category_map.get(category, category),
            count=len(news_items),
            news_list=news_text
        )
        
        # 4. 调用 LLM 并获取 JSON 字符串 (含重试逻辑)
        max_retries = 3
        raw_output = ""
        
        for attempt in range(max_retries):
            raw_output = await self._call_llm(system_prompt, user_prompt)
            
            # 简单验证 JSON 完整性
            # 清洗
            check_text = re.sub(r"^```json\s*", "", raw_output.strip(), flags=re.MULTILINE)
            check_text = re.sub(r"\s*```$", "", check_text, flags=re.MULTILINE)
            
            try:
                json.loads(check_text)
                # 校验成功，跳出循环
                break
            except json.JSONDecodeError:
                print(f"[!] JSON 校验失败 ({attempt+1}/{max_retries})，正在重试: {category}")
                continue
        
        # 5. 直接返回原始 JSON 字符串，由 Renderer 处理渲染
        return raw_output

    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """底层 LLM 调用路由"""
        # 策略 1: Gemini
        if self.model_name == "gemini":
            try:
                MODEL_ID = "gemini-3-pro-preview"
                combined_prompt = f"{system_prompt}\n\nTasks:\n{user_prompt}"
                
                # 使用 self.client (genai.Client)
                response = await self.client.aio.models.generate_content(
                    model=MODEL_ID,
                    contents=combined_prompt,
                    config=types.GenerateContentConfig(
                        thinking_config=types.ThinkingConfig(thinking_level="high"),
                        tools=[
                            # {"url_context": {}}, 
                            {"google_search": {}}
                        ],
                        temperature=0.3,
                        max_output_tokens=10000000
                    )
                )
                return response.text
            except Exception as e:
                return f"Gemini Error: {str(e)}"

        # 策略 2: OpenAI Compatible
        else:
            api_model_map = {
                "deepseek": "deepseek-chat",
                "gpt": "gpt-4o",
                "qwen": "qwen-max", 
            }
            actual_model = api_model_map.get(self.model_name, self.model_name)
            
            try:
                # 使用 self.client (AsyncOpenAI)
                response = await self.client.chat.completions.create(
                    model=actual_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.3
                )
                return response.choices[0].message.content
            except Exception as e:
                return f"LLM Error ({self.model_name}): {str(e)}"

    async def _save_report_files(self, base_path: str, date: datetime.date, category: str, md_content: str) -> str:
        """[Deprecated] 旧版保存逻辑，已由 _handle_file_saving 接管"""
        pass

if __name__ == "__main__":
    async def main():
        MODEL = "gemini"
        SAVE_DIR = r"E:\code\NewsPilot\data\daily_reports"
        analyzer = NewsAnalyzer(model_name=MODEL)

        # 模式1: 聚合分析 (生成一份包含 1月1日-1月30日 信息的综合报告)
        # 为测试使用 2026-01-30 的数据
        start_time = datetime(2026, 1, 28, 0, 0, 0)
        end_time = datetime(2026, 1, 30, 23, 59, 59)
        
        print(f"--- 模式1: 启动长周期聚合分析 ({start_time.date()} ~ {end_time.date()}) ---")
        await analyzer.generate_all_daily_reports(
            time_range=(start_time, end_time),
            md_output_dir=r"E:\code\NewsPilot\data\daily_reports\test\markdown",
            html_output_dir=r"E:\code\NewsPilot\data\daily_reports\test\html",
            pdf_output_dir=r"E:\code\NewsPilot\data\daily_reports\test\pdf",
            save_md_list="ALL",
            save_html_list=["total"],
            save_pdf_list="ALL_CATEGORIES"
        )

        # 模式2 (可选): 逐日回溯 (每天生成一份日报)
        # print(f"\n--- 模式2: 启动逐日历史回溯 ---")
        # current = start_time
        # while current <= end_time:
        #     print(f">>> 生成日报: {current.date()}")
        #     await analyzer.generate_all_daily_reports(
        #         target_date=current.date(),
        #         save_path=SAVE_DIR
        #     )
        #     current += timedelta(days=1)
        #     await asyncio.sleep(2) # 避免限流

        print("\n--- 任务完成 ---")

    asyncio.run(main())
