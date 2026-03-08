#
# Author: WangQiushuo 185886867@qq.com
# Date: 2026-03-06 20:10:00
# LastEditors: WangQiushuo 185886867@qq.com
# LastEditTime: 2026-03-06 20:10:00
# FilePath: \NewsPilot\src\module\agent\project\stock\tools\commodity_data.py
# Description:
# 商品/期货事实工具
#
# Copyright (c) 2026 by , All Rights Reserved.

from typing import Any, Optional

import akshare as ak
import pandas as pd

from src.module.agent.tools.base import Tool


DEFAULT_COMMODITY_LIMIT = 10
SUPPORTED_RECEIPT_EXCHANGES = ["shfe", "dce", "czce", "gfex"]

# 符号代码到中文名称的映射（用于库存查询）
SYMBOL_TO_CHINESE = {
    "AL": "沪铝", "CU": "沪铜", "AU": "沪金", "AG": "沪银", "ZN": "沪锌",
    "PB": "沪铅", "NI": "沪镍", "SN": "沪锡", "RB": "螺纹钢", "HC": "热卷",
    "BU": "沥青", "RU": "橡胶", "FU": "燃油", "A": "豆一", "B": "豆二",
    "M": "豆粕", "Y": "豆油", "P": "棕榈油", "C": "玉米", "CS": "玉米淀粉",
    "JD": "鸡蛋", "L": "塑料", "V": "PVC", "PP": "聚丙烯", "J": "焦炭",
    "JM": "焦煤", "I": "铁矿石", "EG": "乙二醇", "EB": "苯乙烯", "PG": "液化石油气",
    "TA": "PTA", "MA": "甲醇", "CF": "郑棉", "SR": "白糖", "RM": "菜粕",
    "OI": "菜油", "FG": "玻璃", "SA": "纯碱", "UR": "尿素", "CJ": "红枣",
    "AP": "苹果", "SF": "硅铁", "SM": "锰硅", "LH": "生猪", "PK": "花生",
    "SH": "纸浆", "SP": "纸浆", "SS": "不锈钢", "LC": "碳酸锂", "SI": "工业硅",
    "BR": "丁二烯橡胶", "NR": "20号胶", "PF": "短纤", "CY": "棉纱", "PL": "聚乙烯",
    "OP": "胶版印刷纸", "BZ": "纯苯", "PX": "对二甲苯", "AO": "氧化铝", "AD": "集运指数(欧线)",
    "PS": "多晶硅", "LU": "低硫燃料油", "EC": "集运指数(欧线)", "PR": "瓶片",
}


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


def _validate_futures_symbol(symbol: str) -> Optional[str]:
    if not isinstance(symbol, str):
        return "symbol 必须为字符串"
    normalized = symbol.strip().upper()
    if not normalized:
        return "symbol 不能为空"
    if len(normalized) > 10:
        return "symbol 长度异常，请传入标准商品代码，例如 CU、AL、RB、A"
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


def _normalize_futures_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def _convert_symbol_for_inventory(symbol: str) -> str:
    """
    将符号代码转换为库存 API 所需的格式
    优先返回中文名称，如果映射不存在则返回原始符号
    """
    normalized = _normalize_futures_symbol(symbol)
    return SYMBOL_TO_CHINESE.get(normalized, symbol)


def _safe_numeric_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _pick_first_available(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
    return None


# ========== Futures Basis Providers ==========


def _get_basis_from_spot_price(date: str) -> Optional[pd.DataFrame]:
    """期货基差数据（主源）"""
    df = ak.futures_spot_price(date)
    return df if _is_valid_df(df) else None


def _get_basis_from_spot_price_previous(date: str) -> Optional[pd.DataFrame]:
    """期货基差数据（备选 - 前一日数据）"""
    df = ak.futures_spot_price_previous(date)
    return df if _is_valid_df(df) else None


def _get_basis_with_fallback(date: str) -> tuple[Optional[pd.DataFrame], Optional[str], dict]:
    """获取期货基差数据，带 fallback"""
    providers = [
        ("spot_price", _get_basis_from_spot_price),
        ("spot_price_previous", _get_basis_from_spot_price_previous),
    ]
    return _run_fallback_chain(providers, date)


# ========== Inventory Providers ==========


def _get_inventory_from_em(symbol: str) -> Optional[pd.DataFrame]:
    """东财库存数据"""
    # 东财 API 需要中文名称
    chinese_symbol = _convert_symbol_for_inventory(symbol)
    df = ak.futures_inventory_em(symbol=chinese_symbol)
    return df if _is_valid_df(df) else None


def _get_inventory_from_99(symbol: str) -> Optional[pd.DataFrame]:
    """99期货库存数据（备选）"""
    # 99期货 API 也需要中文名称
    chinese_symbol = _convert_symbol_for_inventory(symbol)
    df = ak.futures_inventory_99(symbol=chinese_symbol)
    return df if _is_valid_df(df) else None


def _get_inventory_with_fallback(symbol: str) -> tuple[Optional[pd.DataFrame], Optional[str], dict]:
    """获取库存数据，带 fallback"""
    providers = [
        ("em", _get_inventory_from_em),
        ("99", _get_inventory_from_99),
    ]
    return _run_fallback_chain(providers, symbol)


# ========== Position Rank Providers ==========


def _get_position_rank_from_dce(date: str) -> Optional[dict]:
    """大商所持仓排名数据"""
    rank_dict = ak.futures_dce_position_rank(date=date)
    return rank_dict if rank_dict and isinstance(rank_dict, dict) else None


def _get_position_rank_from_gfex(date: str) -> Optional[dict]:
    """广期所持仓排名数据"""
    rank_dict = ak.futures_gfex_position_rank(date=date)
    return rank_dict if rank_dict and isinstance(rank_dict, dict) else None


def _get_position_rank_with_fallback(exchange: str, date: str) -> tuple[Optional[dict], Optional[str], dict]:
    """获取持仓排名数据，带 fallback"""
    if exchange == "dce":
        providers = [("dce", _get_position_rank_from_dce)]
    else:  # gfex
        providers = [("gfex", _get_position_rank_from_gfex)]
    return _run_fallback_chain(providers, date)


def _get_futures_spot_row(df: pd.DataFrame, symbol: str) -> Optional[pd.Series]:
    if df is None or df.empty:
        return None
    symbol_col = _resolve_column(df, "symbol", "Symbol")
    if not symbol_col:
        return None
    matched = df[df[symbol_col].astype(str).str.upper() == symbol]
    if matched.empty:
        return None
    return matched.iloc[0]


def _summarize_receipt_frame(df: pd.DataFrame) -> dict[str, object]:
    if df is None or df.empty:
        return {}

    current_col = _pick_first_available(df, ["今日仓单量（手）", "仓单数量", "WRTWGHTS"])
    change_col = _pick_first_available(df, ["增减（手）", "当日增减", "WRTCHANGE"])
    location_col = _pick_first_available(df, ["仓库/分库", "仓库简称", "REGNAME"])

    summary = {"记录数": len(df)}

    if current_col:
        current_values = _safe_numeric_series(df[current_col])
        if current_values.notna().any():
            summary["仓单总量"] = current_values.fillna(0).sum()
            summary["最新仓单量字段"] = current_col

    if change_col:
        change_values = _safe_numeric_series(df[change_col])
        if change_values.notna().any():
            summary["当日变化合计"] = change_values.fillna(0).sum()
            summary["变化字段"] = change_col

    if location_col:
        summary["主要维度字段"] = location_col

    return summary


def _extract_receipt_records(df: pd.DataFrame, limit: int) -> list[dict[str, object]]:
    if df is None or df.empty:
        return []

    columns = [col for col in [
        _pick_first_available(df, ["品种代码", "VARNAME"]),
        _pick_first_available(df, ["品种名称"]),
        _pick_first_available(df, ["仓库/分库", "仓库简称", "REGNAME"]),
        _pick_first_available(df, ["今日仓单量（手）", "仓单数量", "WRTWGHTS"]),
        _pick_first_available(df, ["增减（手）", "当日增减", "WRTCHANGE"]),
        _pick_first_available(df, ["有效预报"]),
    ] if col]

    records = []
    for _, row in df.head(limit).iterrows():
        record = {}
        for column in columns:
            record[str(column)] = row[column]
        records.append(record)
    return records


def _extract_position_summary(df: pd.DataFrame, top_n: int) -> dict[str, object]:
    if df is None or df.empty:
        return {}

    top_df = df.head(top_n).copy()
    long_col = _pick_first_available(top_df, ["long_open_interest"])
    short_col = _pick_first_available(top_df, ["short_open_interest"])
    long_chg_col = _pick_first_available(top_df, ["long_open_interest_chg"])
    short_chg_col = _pick_first_available(top_df, ["short_open_interest_chg"])
    vol_col = _pick_first_available(top_df, ["vol"])
    symbol_col = _pick_first_available(top_df, ["symbol"])
    variety_col = _pick_first_available(top_df, ["variety"])

    summary = {"top_n": top_n}

    if symbol_col and top_df[symbol_col].notna().any():
        summary["合约"] = top_df[symbol_col].iloc[0]
    if variety_col and top_df[variety_col].notna().any():
        summary["品种"] = top_df[variety_col].iloc[0]
    if vol_col:
        summary["前N成交量合计"] = _safe_numeric_series(top_df[vol_col]).fillna(0).sum()
    if long_col:
        summary["前N多单持仓合计"] = _safe_numeric_series(top_df[long_col]).fillna(0).sum()
    if short_col:
        summary["前N空单持仓合计"] = _safe_numeric_series(top_df[short_col]).fillna(0).sum()
    if long_chg_col:
        summary["前N多单变化合计"] = _safe_numeric_series(top_df[long_chg_col]).fillna(0).sum()
    if short_chg_col:
        summary["前N空单变化合计"] = _safe_numeric_series(top_df[short_chg_col]).fillna(0).sum()

    return summary


def _extract_position_records(df: pd.DataFrame, top_n: int) -> list[dict[str, object]]:
    if df is None or df.empty:
        return []

    columns = [col for col in [
        _pick_first_available(df, ["rank"]),
        _pick_first_available(df, ["vol_party_name"]),
        _pick_first_available(df, ["vol"]),
        _pick_first_available(df, ["long_party_name"]),
        _pick_first_available(df, ["long_open_interest"]),
        _pick_first_available(df, ["long_open_interest_chg"]),
        _pick_first_available(df, ["short_party_name"]),
        _pick_first_available(df, ["short_open_interest"]),
        _pick_first_available(df, ["short_open_interest_chg"]),
    ] if col]

    records = []
    for _, row in df.head(top_n).iterrows():
        record = {}
        for column in columns:
            record[str(column)] = row[column]
        records.append(record)
    return records


class Commodity_Futures_Basis_Overview(Tool):
    """查询商品现货-期货基差概览"""

    @property
    def name(self) -> str:
        return "commodity_futures_basis_overview"

    @property
    def description(self) -> str:
        return "查询商品现货价格、近月/主力合约价格及基差概览，用于辅助股票产业链分析"

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "商品代码，例如 CU、AL、RB、A；不传则返回全市场概览",
                    },
                    "date": {
                        "type": "string",
                        "description": "查询日期，格式 YYYYMMDD",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "当 symbol 为空时返回前多少条记录",
                        "minimum": 1,
                        "maximum": 50,
                        "default": 10,
                    },
                },
                "required": ["date"],
            }
        }

    async def execute(self, date: str, symbol: Optional[str] = None, limit: int = DEFAULT_COMMODITY_LIMIT) -> str:
        date_error = _validate_date(date)
        if date_error:
            return f"错误: {date_error}"

        normalized_symbol = None
        if symbol is not None and str(symbol).strip():
            symbol_error = _validate_futures_symbol(symbol)
            if symbol_error:
                return f"错误: {symbol_error}"
            normalized_symbol = _normalize_futures_symbol(symbol)

        try:
            df, provider, errors = _get_basis_with_fallback(date)
            if df is None:
                error_msg = "; ".join([f"{k}: {v}" for k, v in errors.items()])
                return f"未查询到 {date} 的商品期货基差数据 (尝试的源: {error_msg})"

            if normalized_symbol:
                row = _get_futures_spot_row(df, normalized_symbol)
                if row is None:
                    return f"未查询到商品 {normalized_symbol} 在 {date} 的基差数据"

                summary = {
                    "品种": row.get("symbol"),
                    "现货价格": row.get("spot_price"),
                    "最近交割合约": row.get("near_contract"),
                    "最近交割合约价格": row.get("near_contract_price"),
                    "主力合约": row.get("dom_contract"),
                    "主力合约价格": row.get("dom_contract_price"),
                    "最近合约基差": row.get("near_basis"),
                    "主力合约基差": row.get("dom_basis"),
                    "最近合约基差率": row.get("near_basis_rate"),
                    "主力合约基差率": row.get("dom_basis_rate"),
                    "日期": row.get("date"),
                }
                records = [summary]
            else:
                recent_df = df.head(limit)
                records = []
                for _, row in recent_df.iterrows():
                    records.append({
                        "品种": row.get("symbol"),
                        "现货价格": row.get("spot_price"),
                        "主力合约": row.get("dom_contract"),
                        "主力合约价格": row.get("dom_contract_price"),
                        "主力合约基差": row.get("dom_basis"),
                        "主力合约基差率": row.get("dom_basis_rate"),
                        "日期": row.get("date"),
                    })

                summary = {
                    "记录数": len(df),
                    "返回条数": len(records),
                    "日期": date,
                }

            lines = [
                "=" * 40,
                "【商品期货基差概览】",
                "",
                f"symbol: {normalized_symbol or 'all'}",
                f"date: {date}",
                f"limit: {limit}",
                "",
                "关键信息:",
                _format_kv_block(summary),
                "",
                "最近记录:",
                _format_records(records),
            ]
            return "\n".join(lines)
        except Exception as e:
            return f"查询商品期货基差概览失败: {str(e)}"


class Commodity_Inventory_Or_Receipt(Tool):
    """查询商品库存或仓单摘要"""

    @property
    def name(self) -> str:
        return "commodity_inventory_or_receipt"

    @property
    def description(self) -> str:
        return "查询商品库存或交易所仓单摘要，用于辅助判断产业链供需和库存压力"

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "商品代码，例如 A、CU、AL、RB",
                    },
                    "data_type": {
                        "type": "string",
                        "description": "查询类型：inventory(库存) / warehouse_receipt(仓单)",
                        "enum": ["inventory", "warehouse_receipt"],
                        "default": "inventory",
                    },
                    "date": {
                        "type": "string",
                        "description": "仓单查询日期，格式 YYYYMMDD；仅 warehouse_receipt 时需要",
                    },
                    "exchange": {
                        "type": "string",
                        "description": "仓单交易所：shfe/dce/czce/gfex；仅 warehouse_receipt 时需要",
                        "enum": ["shfe", "dce", "czce", "gfex"],
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回最近多少条记录",
                        "minimum": 1,
                        "maximum": 30,
                        "default": 10,
                    },
                },
                "required": ["symbol"],
            }
        }

    async def execute(
        self,
        symbol: str,
        data_type: str = "inventory",
        date: Optional[str] = None,
        exchange: Optional[str] = None,
        limit: int = DEFAULT_COMMODITY_LIMIT,
    ) -> str:
        symbol_error = _validate_futures_symbol(symbol)
        if symbol_error:
            return f"错误: {symbol_error}"
        normalized_symbol = _normalize_futures_symbol(symbol)

        try:
            if data_type == "inventory":
                df, provider, errors = _get_inventory_with_fallback(normalized_symbol)
                if df is None:
                    error_msg = "; ".join([f"{k}: {v}" for k, v in errors.items()])
                    return f"未查询到商品 {normalized_symbol} 的库存数据 (尝试的源: {error_msg})"

                recent_df = df.tail(limit)
                date_col = _resolve_column(recent_df, "日期")
                inventory_col = _resolve_column(recent_df, "库存")
                change_col = _resolve_column(recent_df, "增减")
                latest_row = recent_df.iloc[-1]

                summary = {
                    "品种": normalized_symbol,
                    "最新日期": latest_row[date_col] if date_col else None,
                    "最新库存": latest_row[inventory_col] if inventory_col else None,
                    "最新变化": latest_row[change_col] if change_col else None,
                    "样本数": len(df),
                }
                records = []
                for _, row in recent_df.iterrows():
                    records.append({
                        "日期": row[date_col] if date_col else None,
                        "库存": row[inventory_col] if inventory_col else None,
                        "增减": row[change_col] if change_col else None,
                    })
            else:
                date_error = _validate_date(date)
                if date_error:
                    return f"错误: {date_error}"
                if exchange not in SUPPORTED_RECEIPT_EXCHANGES:
                    return f"错误: exchange 必须为 {', '.join(SUPPORTED_RECEIPT_EXCHANGES)}"

                if exchange == "shfe":
                    receipt_data = ak.futures_shfe_warehouse_receipt(date=date)
                elif exchange == "dce":
                    receipt_data = ak.futures_warehouse_receipt_dce(date=date)
                elif exchange == "czce":
                    receipt_data = ak.futures_warehouse_receipt_czce(date=date)
                else:
                    receipt_data = ak.futures_gfex_warehouse_receipt(date=date)

                receipt_df = None
                if isinstance(receipt_data, dict):
                    lookup_keys = [normalized_symbol, normalized_symbol.lower(), normalized_symbol.capitalize()]
                    for key in lookup_keys:
                        if key in receipt_data:
                            receipt_df = receipt_data[key]
                            break
                else:
                    code_col = _pick_first_available(receipt_data, ["品种代码"])
                    if code_col:
                        matched = receipt_data[receipt_data[code_col].astype(str).str.upper() == normalized_symbol]
                        if not matched.empty:
                            receipt_df = matched

                if receipt_df is None or receipt_df.empty:
                    return f"未查询到商品 {normalized_symbol} 在 {exchange} 于 {date} 的仓单数据"

                summary = {
                    "品种": normalized_symbol,
                    "交易所": exchange,
                    "日期": date,
                }
                summary.update(_summarize_receipt_frame(receipt_df))
                records = _extract_receipt_records(receipt_df, limit)

            lines = [
                "=" * 40,
                "【商品库存/仓单摘要】",
                "",
                f"symbol: {normalized_symbol}",
                f"data_type: {data_type}",
                f"exchange: {exchange or 'None'}",
                f"date: {date or 'None'}",
                f"limit: {limit}",
                "",
                "关键信息:",
                _format_kv_block(summary),
                "",
                "最近记录:",
                _format_records(records),
            ]
            return "\n".join(lines)
        except Exception as e:
            return f"查询商品库存/仓单摘要失败: {str(e)}"


class Commodity_Position_Rank_Summary(Tool):
    """查询商品期货持仓排名摘要"""

    @property
    def name(self) -> str:
        return "commodity_position_rank_summary"

    @property
    def description(self) -> str:
        return "查询大商所或广期所的商品期货持仓排名摘要，用于辅助判断资金拥挤度和主力结构"

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "商品代码，例如 JM、A、SI、LC",
                    },
                    "date": {
                        "type": "string",
                        "description": "查询日期，格式 YYYYMMDD",
                    },
                    "exchange": {
                        "type": "string",
                        "description": "交易所：dce/gfex",
                        "enum": ["dce", "gfex"],
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "摘要前N名会员数据",
                        "minimum": 1,
                        "maximum": 20,
                        "default": 5,
                    },
                },
                "required": ["symbol", "date", "exchange"],
            }
        }

    async def execute(self, symbol: str, date: str, exchange: str, top_n: int = 5) -> str:
        symbol_error = _validate_futures_symbol(symbol)
        if symbol_error:
            return f"错误: {symbol_error}"
        date_error = _validate_date(date)
        if date_error:
            return f"错误: {date_error}"

        normalized_symbol = _normalize_futures_symbol(symbol)

        try:
            rank_dict, provider, errors = _get_position_rank_with_fallback(exchange, date)

            if rank_dict is None:
                error_msg = "; ".join([f"{k}: {v}" for k, v in errors.items()])
                return f"未查询到 {exchange} 在 {date} 的持仓排名数据 (尝试的源: {error_msg})"

            matched_contract = None
            matched_df = None
            for contract, df in rank_dict.items():
                contract_upper = str(contract).upper()
                if contract_upper.startswith(normalized_symbol):
                    matched_contract = contract
                    matched_df = df
                    break

            if matched_df is None or matched_df.empty:
                return f"未查询到商品 {normalized_symbol} 在 {exchange} 于 {date} 的持仓排名数据"

            summary = {
                "交易所": exchange,
                "日期": date,
                "匹配合约": matched_contract,
            }
            summary.update(_extract_position_summary(matched_df, top_n))
            records = _extract_position_records(matched_df, top_n)

            lines = [
                "=" * 40,
                "【商品期货持仓排名摘要】",
                "",
                f"symbol: {normalized_symbol}",
                f"exchange: {exchange}",
                f"date: {date}",
                f"top_n: {top_n}",
                "",
                "关键信息:",
                _format_kv_block(summary),
                "",
                "前N明细:",
                _format_records(records),
            ]
            return "\n".join(lines)
        except Exception as e:
            return f"查询商品期货持仓排名摘要失败: {str(e)}"
