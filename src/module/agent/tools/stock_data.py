#
# Author: WangQiushuo 185886867@qq.com
# Date: 2026-03-06 19:45:48
# LastEditors: WangQiushuo 185886867@qq.com
# LastEditTime: 2026-03-08 16:04:17
# FilePath: \NewsPilot\src\module\agent\tools\stock_data.py
# Description:
# A股个股相关工具
#
# Copyright (c) 2026 by , All Rights Reserved.

from typing import Any, Optional

import akshare as ak
import pandas as pd

from src.module.MyTT import EMA, KDJ, MA, MACD, RSI
from src.module.agent.tools.base import Tool


DEFAULT_START_DATE = "20240101"
DEFAULT_HISTORY_LIMIT = 20
DEFAULT_TECHNICAL_LIMIT = 120


# ========== Fallback Infrastructure ==========


def _is_valid_df(df, required_columns: Optional[list[str]] = None) -> bool:
    """检查 DataFrame 是否有效"""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return False
    if required_columns:
        return all(col in df.columns for col in required_columns)
    return True


def _is_valid_series(series) -> bool:
    """检查 Series 是否有效"""
    if series is None or not isinstance(series, pd.Series) or series.empty:
        return False
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


# ========== Symbol Conversion ==========


def _validate_symbol(symbol: str) -> Optional[str]:
    if not isinstance(symbol, str):
        return "symbol 必须为字符串"
    if len(symbol) != 6 or not symbol.isdigit():
        return "symbol 必须为 6 位股票代码字符串，例如 600015 或 000001"
    return None


def _format_scalar(value) -> str:
    if pd.isna(value):
        return "None"
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def _resolve_column(df: pd.DataFrame, *candidates: str) -> Optional[str]:
    for column in df.columns:
        normalized = str(column).replace(" ", "")
        for candidate in candidates:
            if normalized == candidate.replace(" ", ""):
                return column
    return None


def _format_kv_block(data: dict[str, object]) -> str:
    lines = []
    for key, value in data.items():
        lines.append(f"{key}: {_format_scalar(value)}")
    return "\n".join(lines)


def _format_records(records: list[dict[str, object]]) -> str:
    if not records:
        return "无数据"

    lines = []
    for index, record in enumerate(records, start=1):
        lines.append(f"- 记录 {index}")
        for key, value in record.items():
            lines.append(f"  {key}: {_format_scalar(value)}")
    return "\n".join(lines)


def _to_xq_symbol(symbol: str) -> str:
    if symbol.startswith(("6", "9")):
        return f"SH{symbol}"
    return f"SZ{symbol}"


def _to_tx_symbol(symbol: str) -> str:
    if symbol.startswith(("6", "9")):
        return f"sh{symbol}"
    return f"sz{symbol}"


# ========== Profile Providers ==========


def _get_profile_from_xq(symbol: str) -> Optional[dict]:
    """雪球个股基础信息"""
    df = ak.stock_individual_basic_info_xq(symbol=_to_xq_symbol(symbol))
    if not _is_valid_df(df):
        return None

    profile_data = {}
    for _, row in df.iterrows():
        if len(row) < 2:
            continue
        key = str(row.iloc[0]).strip()
        profile_data[key] = row.iloc[1]

    return profile_data if profile_data else None


def _get_profile_from_em(symbol: str) -> Optional[dict]:
    """东财个股基础信息"""
    df = ak.stock_individual_info_em(symbol=symbol)
    if not _is_valid_df(df):
        return None

    profile_data = {}
    item_col = _resolve_column(df, "item", "项目")
    value_col = _resolve_column(df, "value", "值")

    if not item_col or not value_col:
        return None

    for _, row in df.iterrows():
        key = str(row[item_col]).strip()
        profile_data[key] = row[value_col]

    return profile_data if profile_data else None


def _get_profile_with_fallback(symbol: str) -> tuple[Optional[dict], Optional[str], dict]:
    """获取个股基础画像，带 fallback"""
    providers = [
        ("xq", _get_profile_from_xq),
        ("em", _get_profile_from_em),
    ]
    return _run_fallback_chain(providers, symbol)


# ========== Spot Providers ==========


def _get_spot_from_xq(symbol: str) -> Optional[pd.Series]:
    """雪球实时行情"""
    df = ak.stock_individual_spot_xq(symbol=_to_xq_symbol(symbol))
    if not _is_valid_df(df):
        return None

    item_column = _resolve_column(df, "item")
    value_column = _resolve_column(df, "value")
    if not item_column or not value_column:
        return None

    data = {}
    for _, row in df.iterrows():
        key = str(row[item_column]).strip()
        data[key] = row[value_column]

    return pd.Series(data) if data else None


def _get_spot_from_em(symbol: str) -> Optional[pd.Series]:
    """东财实时行情"""
    df = ak.stock_bid_ask_em(symbol=symbol)
    if not _is_valid_df(df):
        return None

    item_col = _resolve_column(df, "item", "项目")
    value_col = _resolve_column(df, "value", "值")

    if not item_col or not value_col:
        return None

    data = {}
    for _, row in df.iterrows():
        key = str(row[item_col]).strip()
        data[key] = row[value_col]

    return pd.Series(data) if data else None


def _get_spot_with_fallback(symbol: str) -> tuple[Optional[pd.Series], Optional[str], dict]:
    """获取实时行情，带 fallback"""
    providers = [
        ("xq", _get_spot_from_xq),
        ("em", _get_spot_from_em),
    ]
    return _run_fallback_chain(providers, symbol)


# ========== Historical Data Providers ==========


def _normalize_hist_df(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """标准化历史行情 DataFrame"""
    if not _is_valid_df(df):
        return df

    normalized_df = df.copy()

    # 确保有 date 列
    date_col = _resolve_column(normalized_df, "date", "日期", "交易日期")
    if date_col and date_col != "date":
        normalized_df["date"] = normalized_df[date_col]

    normalized_df["date"] = pd.to_datetime(normalized_df["date"])

    # 标准化 OHLC 列名
    open_col = _resolve_column(normalized_df, "open", "开盘", "开盘价")
    close_col = _resolve_column(normalized_df, "close", "收盘", "收盘价")
    high_col = _resolve_column(normalized_df, "high", "最高", "最高价")
    low_col = _resolve_column(normalized_df, "low", "最低", "最低价")

    if open_col and open_col != "open":
        normalized_df["open"] = normalized_df[open_col]
    if close_col and close_col != "close":
        normalized_df["close"] = normalized_df[close_col]
    if high_col and high_col != "high":
        normalized_df["high"] = normalized_df[high_col]
    if low_col and low_col != "low":
        normalized_df["low"] = normalized_df[low_col]

    # 处理成交量/成交额
    volume_col = _resolve_column(normalized_df, "volume", "成交量")
    amount_col = _resolve_column(normalized_df, "amount", "成交额")

    if volume_col:
        normalized_df["volume"] = normalized_df[volume_col]
    if amount_col:
        normalized_df["amount"] = normalized_df[amount_col]
    elif not amount_col and volume_col:
        # 如果没有 amount 但有 volume，用 volume 代替
        normalized_df["amount"] = normalized_df[volume_col]

    # 周期聚合
    if period == "weekly":
        normalized_df = (
            normalized_df.set_index("date")
            .resample("W-FRI")
            .agg({
                "open": "first",
                "close": "last",
                "high": "max",
                "low": "min",
                "amount": "sum",
            })
            .dropna(subset=["open", "close", "high", "low"])
            .reset_index()
        )
    elif period == "monthly":
        normalized_df = (
            normalized_df.set_index("date")
            .resample("ME")
            .agg({
                "open": "first",
                "close": "last",
                "high": "max",
                "low": "min",
                "amount": "sum",
            })
            .dropna(subset=["open", "close", "high", "low"])
            .reset_index()
        )

    # 计算涨跌幅和振幅
    normalized_df["涨跌幅"] = ((normalized_df["close"] - normalized_df["open"]) / normalized_df["open"] * 100).where(normalized_df["open"] != 0)
    normalized_df["振幅"] = ((normalized_df["high"] - normalized_df["low"]) / normalized_df["low"] * 100).where(normalized_df["low"] != 0)

    # 输出列
    normalized_df["日期"] = normalized_df["date"].dt.strftime("%Y-%m-%d")
    normalized_df["开盘"] = normalized_df["open"]
    normalized_df["收盘"] = normalized_df["close"]
    normalized_df["最高"] = normalized_df["high"]
    normalized_df["最低"] = normalized_df["low"]
    normalized_df["成交量"] = normalized_df["amount"]
    normalized_df["成交额"] = normalized_df.get("amount", pd.NA)

    return normalized_df


def _get_hist_from_em(
    symbol: str,
    period: str = "daily",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    adjust: str = "",
) -> Optional[pd.DataFrame]:
    """东财历史行情"""
    df = ak.stock_zh_a_hist(
        symbol=symbol,
        period=period,
        start_date=start_date or DEFAULT_START_DATE,
        end_date=end_date or "20500101",
        adjust=adjust,
    )
    if not _is_valid_df(df):
        return None
    return _normalize_hist_df(df, period)


def _get_hist_from_tx(
    symbol: str,
    period: str = "daily",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    adjust: str = "",
) -> Optional[pd.DataFrame]:
    """腾讯历史行情"""
    df = ak.stock_zh_a_hist_tx(
        symbol=_to_tx_symbol(symbol),
        start_date=start_date or DEFAULT_START_DATE,
        end_date=end_date or "20500101",
        adjust=adjust,
    )
    if not _is_valid_df(df):
        return None
    return _normalize_hist_df(df, period)


def _get_hist_df(
    symbol: str,
    period: str = "daily",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    adjust: str = "",
) -> pd.DataFrame:
    """获取历史行情，带 fallback"""
    providers = [
        ("em", _get_hist_from_em),
        ("tx", _get_hist_from_tx),
    ]
    result, provider, errors = _run_fallback_chain(
        providers, symbol, period, start_date, end_date, adjust
    )

    if result is None:
        return pd.DataFrame()

    return result


def _extract_price_snapshot(spot_row: Optional[pd.Series]) -> dict[str, object]:
    if spot_row is None:
        return {}

    field_aliases = [
        ("代码", ["代码"]),
        ("名称", ["名称"]),
        ("最新价", ["最新价", "现价"]),
        ("涨跌幅", ["涨跌幅", "涨幅"]),
        ("涨跌额", ["涨跌额", "涨跌"]),
        ("今开", ["今开"]),
        ("最高", ["最高"]),
        ("最低", ["最低"]),
        ("昨收", ["昨收"]),
        ("成交量", ["成交量"]),
        ("成交额", ["成交额"]),
        ("换手率", ["换手率", "周转率"]),
        ("市盈率-动态", ["市盈率-动态", "市盈率(动)", "市盈率(TTM)"]),
        ("市净率", ["市净率"]),
        ("总市值", ["总市值", "资产净值/总市值"]),
        ("流通市值", ["流通市值", "流通值"]),
        ("时间", ["时间"]),
    ]

    snapshot = {}
    for output_field, candidates in field_aliases:
        for candidate in candidates:
            if candidate in spot_row.index:
                snapshot[output_field] = spot_row[candidate]
                break
    return snapshot


def _build_indicator_commentary(latest_close: float, ema12: float, ema26: float, rsi6: float, macd_value: float) -> list[str]:
    comments = []

    if latest_close >= ema12:
        comments.append("当前价格位于 EMA12 上方")
    else:
        comments.append("当前价格位于 EMA12 下方")

    if ema12 >= ema26:
        comments.append("EMA12 高于 EMA26，短周期相对更强")
    else:
        comments.append("EMA12 低于 EMA26，短周期相对更弱")

    if rsi6 >= 70:
        comments.append("RSI6 处于偏强区间")
    elif rsi6 <= 30:
        comments.append("RSI6 处于偏弱区间")
    else:
        comments.append("RSI6 位于中性区间")

    if macd_value >= 0:
        comments.append("MACD 柱体位于 0 轴上方")
    else:
        comments.append("MACD 柱体位于 0 轴下方")

    return comments


class A_Stock_Profile(Tool):
    """查询A股个股基础画像，并补充最新行情快照"""

    @property
    def name(self) -> str:
        return "a_stock_profile"

    @property
    def description(self) -> str:
        return "查询A股个股基础画像,返回公司基础信息与最新行情快照"

    def get_schema(self):
        """返回工具的 JSON Schema"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "6位股票代码,例如 600015 或 000001",
                        "minLength": 6,
                        "maxLength": 6,
                    }
                },
                "required": ["symbol"],
            }
        }

    async def execute(self, symbol: str) -> str:
        error = _validate_symbol(symbol)
        if error:
            return f"错误: {error}"

        try:
            profile_data, profile_provider, profile_errors = _get_profile_with_fallback(symbol)
            if profile_data is None:
                error_summary = "; ".join([f"{k}: {v}" for k, v in profile_errors.items()])
                return f"未查询到股票 {symbol} 的基础信息 (尝试过: {error_summary})"

            spot_row, spot_provider, spot_errors = _get_spot_with_fallback(symbol)
            spot_data = _extract_price_snapshot(spot_row)

            lines = [
                "=" * 40,
                "【A股个股基础画像】",
                "",
                f"symbol: {symbol}",
                "",
                "基础信息:",
                _format_kv_block(profile_data),
            ]

            if spot_data:
                lines.extend([
                    "",
                    "最新行情:",
                    _format_kv_block(spot_data),
                ])

            return "\n".join(lines)
        except Exception as e:
            return f"查询个股基础画像失败: {str(e)}"


class A_Stock_Price_History(Tool):
    """查询A股个股历史行情"""

    @property
    def name(self) -> str:
        return "a_stock_price_history"

    @property
    def description(self) -> str:
        return "查询A股个股历史行情，返回最近若干条 OHLCV 数据"

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "6位股票代码，例如 600015 或 000001",
                        "minLength": 6,
                        "maxLength": 6,
                    },
                    "period": {
                        "type": "string",
                        "description": "周期：daily/weekly/monthly",
                        "enum": ["daily", "weekly", "monthly"],
                        "default": "daily",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "开始日期，格式 YYYYMMDD",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "结束日期，格式 YYYYMMDD",
                    },
                    "adjust": {
                        "type": "string",
                        "description": "复权方式：空字符串(不复权)/qfq/hfq",
                        "enum": ["", "qfq", "hfq"],
                        "default": "",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回最近多少条记录",
                        "minimum": 1,
                        "maximum": 120,
                        "default": 20,
                    },
                },
                "required": ["symbol"],
            }
        }

    async def execute(
        self,
        symbol: str,
        period: str = "daily",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        adjust: str = "",
        limit: int = DEFAULT_HISTORY_LIMIT,
    ) -> str:
        error = _validate_symbol(symbol)
        if error:
            return f"错误: {error}"

        try:
            df = _get_hist_df(
                symbol=symbol,
                period=period,
                start_date=start_date,
                end_date=end_date,
                adjust=adjust,
            )
            if df is None or df.empty:
                return f"未查询到股票 {symbol} 的历史行情"

            date_col = _resolve_column(df, "日期")
            open_col = _resolve_column(df, "开盘")
            close_col = _resolve_column(df, "收盘")
            high_col = _resolve_column(df, "最高")
            low_col = _resolve_column(df, "最低")
            volume_col = _resolve_column(df, "成交量")
            amount_col = _resolve_column(df, "成交额")
            amplitude_col = _resolve_column(df, "振幅")
            change_col = _resolve_column(df, "涨跌幅")

            recent_df = df.tail(limit)
            records = []
            for _, row in recent_df.iterrows():
                record = {}
                for label, column in [
                    ("日期", date_col),
                    ("开盘", open_col),
                    ("收盘", close_col),
                    ("最高", high_col),
                    ("最低", low_col),
                    ("成交量", volume_col),
                    ("成交额", amount_col),
                    ("振幅", amplitude_col),
                    ("涨跌幅", change_col),
                ]:
                    if column:
                        record[label] = row[column]
                records.append(record)

            lines = [
                "=" * 40,
                "【A股个股历史行情】",
                "",
                f"symbol: {symbol}",
                f"period: {period}",
                f"start_date: {start_date or DEFAULT_START_DATE}",
                f"end_date: {end_date or 'latest'}",
                f"adjust: {adjust or 'none'}",
                f"limit: {limit}",
                "",
                "最近行情:",
                _format_records(records),
            ]
            return "\n".join(lines)
        except Exception as e:
            return f"查询个股历史行情失败: {str(e)}"


class A_Stock_Technical_Indicators(Tool):
    """基于历史行情和 MyTT 计算常用技术指标"""

    @property
    def name(self) -> str:
        return "a_stock_technical_indicators"

    @property
    def description(self) -> str:
        return "查询A股个股历史行情并使用 MyTT 计算常用技术指标，如 EMA、MA、RSI、MACD、KDJ"

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "6位股票代码，例如 600015 或 000001",
                        "minLength": 6,
                        "maxLength": 6,
                    },
                    "period": {
                        "type": "string",
                        "description": "周期：daily/weekly/monthly",
                        "enum": ["daily", "weekly", "monthly"],
                        "default": "daily",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "开始日期，格式 YYYYMMDD；不传则使用默认足够长的窗口",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "结束日期，格式 YYYYMMDD",
                    },
                    "adjust": {
                        "type": "string",
                        "description": "复权方式：空字符串(不复权)/qfq/hfq",
                        "enum": ["", "qfq", "hfq"],
                        "default": "hfq",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "用于指标计算的历史样本条数下限",
                        "minimum": 60,
                        "maximum": 500,
                        "default": 120,
                    },
                },
                "required": ["symbol"],
            }
        }

    async def execute(
        self,
        symbol: str,
        period: str = "daily",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        adjust: str = "hfq",
        limit: int = DEFAULT_TECHNICAL_LIMIT,
    ) -> str:
        error = _validate_symbol(symbol)
        if error:
            return f"错误: {error}"

        try:
            df = _get_hist_df(
                symbol=symbol,
                period=period,
                start_date=start_date or "20230101",
                end_date=end_date,
                adjust=adjust,
            )
            if df is None or df.empty:
                return f"未查询到股票 {symbol} 的历史行情，无法计算技术指标"

            if len(df) < 30:
                return f"历史行情不足，当前仅有 {len(df)} 条记录，无法稳定计算常用技术指标"

            if len(df) < limit:
                calc_df = df.copy()
            else:
                calc_df = df.tail(limit).copy()

            date_col = _resolve_column(calc_df, "日期")
            close_col = _resolve_column(calc_df, "收盘")
            high_col = _resolve_column(calc_df, "最高")
            low_col = _resolve_column(calc_df, "最低")
            open_col = _resolve_column(calc_df, "开盘")
            volume_col = _resolve_column(calc_df, "成交量")

            required_columns = [date_col, close_col, high_col, low_col]
            if any(column is None for column in required_columns):
                return "历史行情字段不完整，无法计算技术指标"

            close_series = pd.to_numeric(calc_df[close_col], errors="coerce").astype(float).values
            high_series = pd.to_numeric(calc_df[high_col], errors="coerce").astype(float).values
            low_series = pd.to_numeric(calc_df[low_col], errors="coerce").astype(float).values
            open_series = pd.to_numeric(calc_df[open_col], errors="coerce").astype(float).values if open_col else None
            volume_series = pd.to_numeric(calc_df[volume_col], errors="coerce").astype(float).values if volume_col else None

            ema12 = EMA(close_series, 12)
            ema26 = EMA(close_series, 26)
            ma5 = MA(close_series, 5)
            ma10 = MA(close_series, 10)
            ma20 = MA(close_series, 20)
            rsi6 = RSI(close_series, 6)
            rsi12 = RSI(close_series, 12)
            dif, dea, macd = MACD(close_series, 12, 26, 9)
            k_value, d_value, j_value = KDJ(close_series, high_series, low_series, 9, 3, 3)

            latest_row = calc_df.iloc[-1]
            latest_date = latest_row[date_col]
            latest_close = float(close_series[-1])

            summary = {
                "最新交易日": latest_date,
                "最新收盘价": latest_close,
                "EMA12": ema12[-1],
                "EMA26": ema26[-1],
                "MA5": ma5[-1],
                "MA10": ma10[-1],
                "MA20": ma20[-1],
                "RSI6": rsi6[-1],
                "RSI12": rsi12[-1],
                "MACD_DIF": dif[-1],
                "MACD_DEA": dea[-1],
                "MACD": macd[-1],
                "K": k_value[-1],
                "D": d_value[-1],
                "J": j_value[-1],
            }

            if open_series is not None:
                summary["最新开盘价"] = open_series[-1]
            if volume_series is not None:
                summary["最新成交量"] = volume_series[-1]

            comments = _build_indicator_commentary(
                latest_close=latest_close,
                ema12=float(ema12[-1]),
                ema26=float(ema26[-1]),
                rsi6=float(rsi6[-1]),
                macd_value=float(macd[-1]),
            )

            lines = [
                "=" * 40,
                "【A股个股技术指标】",
                "",
                f"symbol: {symbol}",
                f"period: {period}",
                f"start_date: {start_date or '20230101'}",
                f"end_date: {end_date or 'latest'}",
                f"adjust: {adjust or 'none'}",
                f"samples: {len(calc_df)}",
                "",
                "关键信息:",
                _format_kv_block(summary),
                "",
                "说明:",
            ]
            lines.extend([f"- {comment}" for comment in comments])
            return "\n".join(lines)
        except Exception as e:
            return f"计算个股技术指标失败: {str(e)}"
