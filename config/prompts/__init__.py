"""
Prompts 统一导出
"""

# 数据处理Prompts
from .data_processing_prompt import (
    TRANSLATION_BATCH_PROMPT_CN,
    REFINE_CLASSIFY_SCORE_PROMPT_CN,
    Image_Vision_PROMPT_CN,
)

# 日报生成Prompts
from .daily_report_prompt import (
    CATEGORY_DAILY_REPORT_PROMPT,
    TOTAL_DAILY_REPORT_PROMPT,
    PERSONALIZED_INSIGHT_PROMPT,
)

# Agent分析Prompts
# from .agent_analysis_prompt import (

# )

# 知乎分析Prompts
from .zhihu_analysis_prompt import (
    ZHIHU_MRDANG_ANALYSIS_PROMPT_CN,
)

__all__ = [
    # 数据处理Prompts
    "TRANSLATION_BATCH_PROMPT_CN",
    "REFINE_CLASSIFY_SCORE_PROMPT_CN",
    "Image_Vision_PROMPT_CN",
    # 日报生成Prompts
    "CATEGORY_DAILY_REPORT_PROMPT",
    "TOTAL_DAILY_REPORT_PROMPT",
    "PERSONALIZED_INSIGHT_PROMPT",
    # Agent分析Prompts
    # ...
    # 知乎分析Prompts
    "ZHIHU_MRDANG_ANALYSIS_PROMPT_CN",
]