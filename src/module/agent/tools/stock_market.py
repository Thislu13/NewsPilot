#
# Author: WangQiushuo 185886867@qq.com
# Date: 2026-03-04 23:19:28
# LastEditors: WangQiushuo 185886867@qq.com
# LastEditTime: 2026-03-06 19:46:02
# FilePath: \NewsPilot\src\module\agent\project\stock\tools\stock_market.py
# Description:
# 市场整体局势的统一工具
#
# Copyright (c) 2026 by , All Rights Reserved.

from typing import Any, Optional

import akshare as ak
import pandas as pd

from src.module.agent.tools.base import Tool


# ========== Fallback Infrastructure ==========


def _is_valid_df(df, required_columns: Optional[list[str]] = None) -> bool:
    """检查 DataFrame 是否有效"""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return False
    if required_columns:
        return all(col in df.columns for col in required_columns)
    return True


def _run_fallback_chain(providers: list[tuple[str, callable]], *args, **kwargs):
    """
    按顺序尝试多个 provider，返回第一个有效结果
    providers: [(provider_name, provider_func), ...]
    返回: (result, provider_name, errors)
    """
    errors = {}
    for provider_name, provider_func in providers:
        try:
            result = provider_func(*args, **kwargs)
            if result is not None:
                return result, provider_name, errors
            errors[provider_name] = "returned None"
        except Exception as e:
            errors[provider_name] = str(e)
    return None, None, errors


# ========== Validation and Formatting ==========


def _validate_date(date: Optional[str]) -> Optional[str]:
    if date is None:
        return "date 不能为空，格式应为 YYYYMMDD"
    if not isinstance(date, str):
        return "date 必须为字符串，格式应为 YYYYMMDD"
    if len(date) != 8 or not date.isdigit():
        return "date 必须为 8 位日期字符串，格式应为 YYYYMMDD"
    return None


def _format_scalar(value) -> str:
    if pd.isna(value):
        return "None"
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def _format_kv_block(data: dict[str, object]) -> str:
    lines = []
    for key, value in data.items():
        lines.append(f"{key}: {_format_scalar(value)}")
    return "\n".join(lines)


def _format_row_value_pairs(df: pd.DataFrame) -> str:
    data_dict = {}
    for _, row in df.iterrows():
        if len(row) < 2:
            continue
        key = str(row.iloc[0]).strip()
        data_dict[key] = row.iloc[1]
    return _format_kv_block(data_dict)


def _format_grouped_rows(df: pd.DataFrame) -> str:
    columns = df.columns.tolist()
    lines = []

    for _, row in df.iterrows():
        group_name = str(row.iloc[0]).strip()
        lines.append(f"{group_name}:")

        for col_idx in range(1, len(columns)):
            col_name = columns[col_idx]
            value = row.iloc[col_idx]
            lines.append(f"  {col_name}: {_format_scalar(value)}")

        lines.append("")

    return "\n".join(lines).rstrip()


# ========== Market Activity Providers ==========


def _get_activity_from_legu() -> Optional[pd.DataFrame]:
    """乐咕乐股市场活跃度"""
    df = ak.stock_market_activity_legu()
    return df if _is_valid_df(df) else None


def _get_activity_with_fallback() -> tuple[Optional[pd.DataFrame], Optional[str], dict]:
    """获取市场活跃度，带 fallback"""
    providers = [
        ("legu", _get_activity_from_legu),
    ]
    return _run_fallback_chain(providers)


# ========== SSE Summary Providers ==========


def _get_sse_from_summary() -> Optional[pd.DataFrame]:
    """上交所股票数据总貌"""
    df = ak.stock_sse_summary()
    return df if _is_valid_df(df) else None


def _get_sse_from_deal_daily(date: Optional[str] = None) -> Optional[pd.DataFrame]:
    """上交所每日概况（备选）"""
    if not date:
        # 如果没有提供日期，尝试获取最近的交易日
        from datetime import datetime, timedelta
        date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

    df = ak.stock_sse_deal_daily(date=date)
    return df if _is_valid_df(df) else None


def _get_sse_with_fallback(date: Optional[str] = None) -> tuple[Optional[pd.DataFrame], Optional[str], dict]:
    """获取上交所总貌，带 fallback"""
    providers = [
        ("summary", _get_sse_from_summary),
        ("deal_daily", lambda: _get_sse_from_deal_daily(date)),
    ]
    return _run_fallback_chain(providers)


# ========== SZSE Summary Providers ==========


def _get_szse_from_summary(date: str) -> Optional[pd.DataFrame]:
    """深交所市场总貌"""
    df = ak.stock_szse_summary(date=date)
    return df if _is_valid_df(df) else None


def _get_szse_from_sector(date: str) -> Optional[pd.DataFrame]:
    """深交所行业成交（备选）"""
    # 将 YYYYMMDD 转换为 YYYYMM
    year_month = date[:6]
    df = ak.stock_szse_sector_summary(symbol="当年", date=year_month)
    return df if _is_valid_df(df) else None


def _get_szse_with_fallback(date: str) -> tuple[Optional[pd.DataFrame], Optional[str], dict]:
    """获取深交所总貌，带 fallback"""
    providers = [
        ("summary", lambda: _get_szse_from_summary(date)),
        ("sector", lambda: _get_szse_from_sector(date)),
    ]
    return _run_fallback_chain(providers)


class A_Stock_Market_Overview(Tool):
    """查询A股市场总貌统一工具，支持市场活跃度、上交所总貌、深交所总貌"""

    @property
    def name(self) -> str:
        return "a_stock_market_overview"

    @property
    def description(self) -> str:
        return (
            "查询A股市场总貌数据，支持三种查询类型：\n"
            "1. activity - 市场活跃度（涨跌停统计、赚钱效应分析）\n"
            "2. sse - 上海证券交易所股票数据总貌（流通股本、市值、市盈率等）\n"
            "3. szse - 深圳证券交易所市场总貌（证券类别统计，需提供日期）\n"
            "4. all - 查询所有市场数据（需提供日期用于深交所查询）"
        )

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "market_type": {
                        "type": "string",
                        "description": "市场类型：activity(市场活跃度)、sse(上交所)、szse(深交所)、all(全部)",
                        "enum": ["activity", "sse", "szse", "all"],
                        "default": "activity"
                    },
                    "date": {
                        "type": "string",
                        "description": "查询日期，格式 YYYYMMDD，仅在 market_type 为 szse 或 all 时需要"
                    }
                },
                "required": ["market_type"]
            }
        }

    async def execute(self, market_type: str = "activity", date: Optional[str] = None) -> str:
        """执行市场总貌查询并返回结构化纯文本结果。"""
        results = []

        try:
            if market_type in ["szse", "all"]:
                date_error = _validate_date(date)
                if date_error:
                    return f"错误: {date_error}"

            if market_type in ["activity", "all"]:
                activity_data = await self._get_market_activity()
                results.extend([
                    "=" * 40,
                    "【A股市场活跃度】",
                    "",
                    f"market_type: {market_type}",
                    f"date: {date or 'None'}",
                    "",
                    activity_data,
                    "",
                ])

            if market_type in ["sse", "all"]:
                sse_data = await self._get_sse_summary()
                results.extend([
                    "=" * 40,
                    "【上海证券交易所股票数据总貌】",
                    "",
                    f"market_type: {market_type}",
                    f"date: {date or 'None'}",
                    "",
                    sse_data,
                    "",
                ])

            if market_type in ["szse", "all"]:
                szse_data = await self._get_szse_summary(date)
                results.extend([
                    "=" * 40,
                    f"【深圳证券交易所市场总貌 ({date})】",
                    "",
                    f"market_type: {market_type}",
                    f"date: {date}",
                    "",
                    szse_data,
                    "",
                ])

            if not results:
                return f"错误: 不支持的market_type: {market_type}"

            return "\n".join(results).rstrip()

        except Exception as e:
            return f"查询市场总貌失败: {str(e)}"

    async def _get_market_activity(self) -> str:
        """获取市场活跃度数据，带 fallback"""
        df, provider, errors = _get_activity_with_fallback()
        if df is None:
            error_summary = "; ".join([f"{k}: {v}" for k, v in errors.items()])
            raise Exception(f"无法获取市场活跃度数据 (尝试过: {error_summary})")
        return _format_row_value_pairs(df)

    async def _get_sse_summary(self, date: Optional[str] = None) -> str:
        """获取上交所股票数据总貌，带 fallback"""
        df, provider, errors = _get_sse_with_fallback(date)
        if df is None:
            error_summary = "; ".join([f"{k}: {v}" for k, v in errors.items()])
            raise Exception(f"无法获取上交所总貌数据 (尝试过: {error_summary})")
        return _format_grouped_rows(df)

    async def _get_szse_summary(self, date: str) -> str:
        """获取深交所市场总貌，带 fallback"""
        df, provider, errors = _get_szse_with_fallback(date)
        if df is None:
            error_summary = "; ".join([f"{k}: {v}" for k, v in errors.items()])
            raise Exception(f"无法获取深交所总貌数据 (尝试过: {error_summary})")
        return _format_grouped_rows(df)
