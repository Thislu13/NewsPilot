"""
知乎报告渲染器工厂
Factory for creating Zhihu report renderers based on author configuration
"""

from typing import Type

from .zhihu_mrdang_report import ZhihuMRDangReportRenderer
from src.custom_logging import get_logger

logger = get_logger(__name__)

# Registry of available renderer classes
RENDERER_REGISTRY = {
    "ZhihuMRDangReportRenderer": ZhihuMRDangReportRenderer,
    # Future renderers can be registered here:
    # "ZhihuAnotherReportRenderer": ZhihuAnotherReportRenderer,
}

def get_renderer_class(renderer_class_name: str) -> Type:
    """
    Get renderer class by name.

    Args:
        renderer_class_name: Name of the renderer class

    Returns:
        Renderer class (not instance)

    Raises:
        ValueError: If renderer class not found in registry
    """
    renderer_class = RENDERER_REGISTRY.get(renderer_class_name)

    if renderer_class is None:
        logger.error(f"Renderer class '{renderer_class_name}' not found in registry")
        raise ValueError(f"Unknown renderer class: {renderer_class_name}")

    return renderer_class

def create_renderer(renderer_class_name: str):
    """
    Create a renderer instance by class name.

    Args:
        renderer_class_name: Name of the renderer class

    Returns:
        Renderer instance
    """
    renderer_class = get_renderer_class(renderer_class_name)
    return renderer_class()
