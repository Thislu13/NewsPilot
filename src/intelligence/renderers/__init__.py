from .daily_report import DailyReportRenderer
from .daily_total_report import DailyTotalReportRenderer
from .zhihu_report import ZhihuMRDangReportRenderer

# Backward compatibility alias
ZhihuDangReportRenderer = ZhihuMRDangReportRenderer

__all__ = [
    "DailyReportRenderer",
    "DailyTotalReportRenderer",
    "ZhihuMRDangReportRenderer",
    "ZhihuDangReportRenderer",  # Keep for backward compatibility
]