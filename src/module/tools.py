#
# Author: WangQiushuo 185886867@qq.com
# Date: 2026-01-31 20:01:33
# LastEditors: WangQiushuo 185886867@qq.com
# LastEditTime: 2026-01-31 20:01:39
# FilePath: \NewsPilot\src\module\uuid_v7.py
# Description: 通用工具函数模块
# 
# Copyright (c) 2026 by , All Rights Reserved. 

# 生成时间有序 ID (UUIDv7 模拟) 以优化数据库写入性能
# 这里的实现模拟了 UUIDv7 格式：Timestamp(48bit) + Random(80bit)
import time
import random
import uuid
from typing import Optional
from urllib.parse import urlparse
import re
import unicodedata
from typing import Iterable

def generate_uuid7() -> str:
    """生成时间有序的 UUIDv7"""
    u_int = (int(time.time() * 1000) << 80) | random.getrandbits(80)
    # Version 7 (0111) at bits 76-79
    u_int = (u_int & ~(0xF << 76)) | (0x7 << 76)
    # Variant 1 (10) at bits 62-63
    u_int = (u_int & ~(0xC << 62)) | (0x8 << 62)
    unique_id_v7 = str(uuid.UUID(int=u_int))

    return unique_id_v7

def extract_host(url: str) -> Optional[str]:
    """从 URL 中提取 host。

    - 支持标准 URL（带 scheme）
    - 兼容裸域名/不带 scheme 的情况（如 example.com/path）
    """

    if not url:
        return None

    parsed = urlparse(url)
    if parsed.netloc:
        return parsed.netloc.lower()

    # 兼容没有 scheme 的 URL：example.com/path
    parsed2 = urlparse(f"http://{url}")
    return parsed2.netloc.lower() if parsed2.netloc else None


def normalize_text(
    text: str,
    *,
    normalize_unicode: bool = True,
    normalize_whitespace: bool = True,
    normalize_punctuation: bool = True,
    remove_web_noise: bool = True,
    compress_structure: bool = True,
) -> str:
    """
    通用文本规范化函数（中英通用，LLM / embedding 友好）

    设计目标：
    - 语义不变
    - 减少无意义 token
    - 输出稳定
    """

    if not text:
        return ""

    # ======================
    # 1. Unicode 统一
    # ======================
    if normalize_unicode:
        # 全角/半角、组合字符、兼容字符统一
        text = unicodedata.normalize("NFKC", text)

    # ======================
    # 2. 换行 & 空白规范
    # ======================
    if normalize_whitespace:
        # 统一换行符
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # 行首/行尾空白（含全角）
        text = re.sub(
            r'^[ \t\u3000]+|[ \t\u3000]+$',
            '',
            text,
            flags=re.MULTILINE,
        )

        # 多个空格压缩为 1 个（英文关键）
        text = re.sub(r'[ \t]{2,}', ' ', text)

        # 3 个及以上换行压缩为 2 个
        text = re.sub(r'\n{3,}', '\n\n', text)

    # ======================
    # 3. 标点符号规范
    # ======================
    if normalize_punctuation:
        punctuation_map = {
            '，': ',',
            '。': '.',
            '：': ':',
            '；': ';',
            '！': '!',
            '？': '?',
            '（': '(',
            '）': ')',
            '【': '[',
            '】': ']',
            '《': '<',
            '》': '>',
        }

        for k, v in punctuation_map.items():
            text = text.replace(k, v)

        # 连续标点压缩
        text = re.sub(r'([.!?]){2,}', r'\1', text)

    # ======================
    # 4. 网页噪声清理
    # ======================
    if remove_web_noise:
        noise_patterns: Iterable[str] = [
            r'^\s*本文来源[:：].*$',
            r'^\s*责任编辑[:：].*$',
            r'^\s*版权声明.*$',
            r'^\s*未经许可.*$',
            r'^\s*点击.*?(阅读全文|阅读更多).*$',
            r'^\s*Read more.*$',
            r'^\s*Related articles.*$',
            r'^\s*All rights reserved.*$',
        ]

        for p in noise_patterns:
            text = re.sub(p, '', text, flags=re.MULTILINE | re.IGNORECASE)

    # ======================
    # 5. 结构压缩（保语义）
    # ======================
    if compress_structure:
        # 统一列表符号
        text = re.sub(r'^[•·–—\-]+', '-', text, flags=re.MULTILINE)

        # 多余空行再压一次（防止上面步骤引入）
        text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()
