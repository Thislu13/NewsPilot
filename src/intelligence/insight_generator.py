# src/intelligence/insight_generator.py
"""
洞察生成器 - 依赖用户画像，生成个性化建议
"""

from typing import List

from datetime import datetime
from google import genai
from google.genai import types
from google.genai.types import GenerateContentConfig, ThinkingConfig, Tool


from core.news_schemas import NewsItemRefinedSchema
# from core.analysis_schemas import PersonalizedInsights, Insight
# from core.user_schemas import UserProfileSchema
from src.module.init_client import LLMClientFactory
from config.prompts import PERSONALIZED_INSIGHT_PROMPT

class InsightGenerator:
    """
    个性化洞察生成器
    
    职责：
    - 结合用户画像生成个性化建议
    - 识别机会与风险
    - 提供行动建议
    
    依赖：
    - 用户画像（通过接口获取）
    - 新闻数据
    - (可选)历史记忆
    """
    
    def __init__(self, model_name: str = "deepseek"):

        factory = LLMClientFactory()
        self.llm = factory.get_client(model_name)
        self.model_name = model_name
    
    def generate_insights(
        self,
        news_items: List[NewsItemRefinedSchema],
        user_profile = None,
        daily_digest: str = None  # 可选：基于已生成的摘要
    ):
        """
        生成个性化洞察
        
        Args:
            news_items: 新闻列表
            user_profile: 用户画像（由外部传入）
            daily_digest: 可选的每日摘要（避免重复分析）
        """
        # 准备用户画像文本
        profile_text = self._format_profile(user_profile)
        
        # 准备新闻文本（如果没有摘要）
        if daily_digest:
            context = f"今日新闻摘要：\n{daily_digest}"
        else:
            context = self._format_news(news_items)
        
        # 调用 LLM
        system_prompt = PERSONALIZED_INSIGHT_PROMPT["SYSTEM_PROMPT"]
        user_prompt = PERSONALIZED_INSIGHT_PROMPT["USER_PROMPT_TEMPLATE"].format(
            user_profile=profile_text,
            news_context=context,
            current_date=datetime.now().strftime("%Y-%m-%d")
        )
        full_prompt = f"{system_prompt}\n{user_prompt}"
        response =self.llm.models.generate_content(
            model="gemini-3-pro-preview",
            contents=full_prompt,
            config=GenerateContentConfig(
                thinking_config=ThinkingConfig(thinking_level="high"),
                tools=[
                    # {"url_context": {}}, 
                    {"google_search": {}}
                ],
                temperature=0.7,
                max_output_tokens=10000000
            ),
        )
        
        insights_text = response.text
        
        # 解析结构化洞察（可以进一步优化为 JSON 输出）
        # insights = self._parse_insights(insights_text)
        print("生成的个性化洞察内容：")
        print(insights_text)
        return {
            "user_id": '0001',
            "date": news_items[0].published_at.strftime("%Y-%m-%d"),
            "insights": insights_text,
            # "raw_output": insights_text
        }
    
    def _format_profile(self, profile) -> str:
        """格式化用户画像"""
        user_profile_path = "config/user_profile.json"
        with open(user_profile_path, 'r', encoding='utf-8') as f:
            profile_data = f.read()

        return profile_data
        # parts = []
        
        # if profile.background:
        #     bg = profile.background
        #     parts.append(f"职业：{bg.get('occupation', '未知')}")
        #     parts.append(f"行业：{bg.get('industry', '未知')}")
        #     if bg.get('expertise'):
        #         parts.append(f"专业领域：{', '.join(bg['expertise'])}")
        
        # if profile.interests:
        #     interests = "\n".join([
        #         f"  - {i.category}（关注度{i.weight}）：{', '.join(i.keywords[:5])}"
        #         for i in profile.interests
        #     ])
        #     parts.append(f"关注领域：\n{interests}")
        
        # return "\n".join(parts)
    
    def _format_news(self, news_items: List[NewsItemRefinedSchema]) -> str:
        # 同 NewsAnalyzer
        formatted = []
        for i, item in enumerate(news_items, 1):
            formatted.append(
                f"{i}. [{item.source_channel}] {item.title}\n"
                f"   时间：{item.published_at.strftime('%Y-%m-%d')}\n"
                f"   摘要：{item.abstract[:200]}...\n"
                # f"   链接：{item.source_url}"
            )
        return "\n".join(formatted)
    
        # def _parse_insights(self, text: str) -> List[Insight]:
        #     """
        #     解析 LLM 输出为结构化洞察
        #     （简化版，实际可以用 JSON mode 或正则提取）
        #     """
        #     # 暂时返回单个洞察
        #     return [
        #         Insight(
        #             type="general",
        #             title="综合洞察",
        #             content=text,
        #             relevance_score=0.8,
        #             action_items=[]
        #         )
        #     ]
    


if __name__ == "__main__":
    import asyncio
    from pathlib import Path
    import json
    from dateutil.parser import parse
    from core.news_schemas import NewsItemRefinedSchema

    # 加载示例新闻数据
    news_path = r'E:\code\NewsPilot\data\temp\news\refined_news_items.json'
    with open(Path(news_path), "r", encoding="utf-8") as f:
        news_data = json.load(f)

    def normalize_news_item(item: dict) -> dict:
        if "published_at" in item and isinstance(item["published_at"], str):
            item["published_at"] = parse(item["published_at"])
        return item

    news_items = [NewsItemRefinedSchema(**normalize_news_item(item)) for item in news_data[:5]]

    # 加载示例用户画像
    user_profile_path = r'E:\code\NewsPilot\data\user_profile.json'
    with open(user_profile_path, "r", encoding="utf-8") as f:
        profile_data = json.load(f)
    # user_profile = UserProfileSchema(**profile_data)

    # 生成洞察
    generator = InsightGenerator(model_name="gemini")
    insights = generator.generate_insights(news_items)
    print("生成的个性化洞察：")

    save_path = Path(r"E:\code\NewsPilot\data\temp\personalized_insights.json")
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(insights, f, ensure_ascii=False, indent=4)