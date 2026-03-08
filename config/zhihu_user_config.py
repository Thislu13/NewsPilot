"""
知乎用户配置映射
Maps author identifiers to their specific prompts and renderers
"""

from typing import Dict
import logging

# Import prompts
from config.prompts.zhihu_analysis_prompt import ZHIHU_MRDANG_ANALYSIS_PROMPT_CN

logger = logging.getLogger("ZhihuUserConfig")

# Author identifier mapping
# Key: author identifier from database (ZhihuRawPost.author)
# Value: dict with prompt and renderer_class_name
ZHIHU_AUTHOR_CONFIG: Dict[str, Dict] = {
    "mr-dang-77": {
        "prompt": ZHIHU_MRDANG_ANALYSIS_PROMPT_CN,
        "renderer_class_name": "ZhihuMRDangReportRenderer",
        "display_name": "MR Dang",
    },
    # Future users can be added here:
    # "another-author-id": {
    #     "prompt": ZHIHU_ANOTHER_ANALYSIS_PROMPT_CN,
    #     "renderer_class_name": "ZhihuAnotherReportRenderer",
    #     "display_name": "Another Author",
    # },
}

# Default fallback configuration
DEFAULT_AUTHOR_CONFIG = {
    "prompt": ZHIHU_MRDANG_ANALYSIS_PROMPT_CN,
    "renderer_class_name": "ZhihuMRDangReportRenderer",
    "display_name": "Unknown Author (using MR Dang template)",
}

def get_author_config(author: str) -> Dict:
    """
    Get configuration for a specific author.
    Falls back to default if author not found.

    Args:
        author: Author identifier from database

    Returns:
        Dict with prompt, renderer_class_name, and display_name
    """
    if not author:
        logger.warning("No author provided, using default configuration")
        return DEFAULT_AUTHOR_CONFIG

    config = ZHIHU_AUTHOR_CONFIG.get(author)
    if config is None:
        logger.warning(f"Unknown author '{author}', using default configuration")
        return DEFAULT_AUTHOR_CONFIG

    return config
