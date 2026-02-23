"""
通用附件下载工具模块

提供统一的附件下载和处理功能，支持所有fetchers使用。
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup

from core.news_schemas import Attachment, NewsItemRawSchema


def extract_attachment_urls_from_html(html: str) -> tuple[str, List[Dict[str, Any]]]:
    """
    从HTML中提取附件URL并替换为占位符（不下载）

    Args:
        html: HTML内容

    Returns:
        (body_text, attachment_dicts): 提取文本后的body（媒体标签已替换为<attach_n>）和附件字典列表
    """
    if not html:
        return "", []

    soup = BeautifulSoup(html, "html.parser")
    attachment_dicts: List[Dict[str, Any]] = []
    media_tags = soup.find_all(["img", "video"])

    for tag in media_tags:
        media_type = "image" if tag.name == "img" else "video"
        media_url = ""

        if media_type == "image":
            media_url = tag.get("src") or tag.get("data-original") or ""
        else:
            media_url = tag.get("src") or ""
            if not media_url:
                source_tag = tag.find("source")
                if source_tag:
                    media_url = source_tag.get("src") or ""

        media_url = (media_url or "").strip()
        if not media_url:
            continue

        # 创建附件字典（file_id为None，稍后可由enrich_attachment填充）
        attachment_dicts.append({
            "type": media_type,
            "url": media_url,
            "caption": tag.get("alt") or tag.get("title") or None,
            "file_id": None,
        })

        # 替换媒体标签为占位符
        placeholder = f"<attach_{len(attachment_dicts) - 1}>"
        tag.replace_with(placeholder)

    # 提取纯文本（媒体标签已被替换为占位符）
    body = soup.get_text("\n", strip=True)
    body = re.sub(r"\n{2,}", "\n", body).strip()
    return body, attachment_dicts


async def enrich_attachment(
    normalized_list: List[NewsItemRawSchema],
    download_root: Path = Path("data/attachments"),
    prefix: str = "zhihu",
    replace_with_placeholder: bool = True
) -> List[NewsItemRawSchema]:
    """
    下载附件并填充file_id字段

    Args:
        normalized_list: 已标准化的新闻列表
        download_root: 下载根目录
        prefix: 文件名前缀（如"zhihu", "rsshub"）
        replace_with_placeholder: 是否在body中用<attach_n>替换原始媒体标签

    Returns:
        enriched的新闻列表，attachments中的file_id已填充
    """
    enriched_list = []

    for item in normalized_list:
        if not item.attachments:
            enriched_list.append(item)
            continue

        # 下载每个附件
        enriched_attachments = []
        for idx, att in enumerate(item.attachments):
            if att.file_id:  # 已经下载过
                enriched_attachments.append(att)
                continue

            # 下载文件
            file_id = await _download_attachment(
                url=att.url,
                media_type=att.type,
                source_id=item.source_id,
                published_at=item.published_at,
                index=idx,
                download_root=download_root,
                prefix=prefix
            )

            # 创建新的Attachment对象，填充file_id
            enriched_att = att.model_copy(update={"file_id": file_id})
            enriched_attachments.append(enriched_att)

        # 可选：替换body中的媒体标签为占位符
        new_body = item.body
        if replace_with_placeholder:
            new_body = _replace_media_with_placeholders(item.body, enriched_attachments)

        # 创建新的NewsItemRawSchema
        enriched_item = item.model_copy(update={
            "body": new_body,
            "attachments": enriched_attachments
        })
        enriched_list.append(enriched_item)

    return enriched_list


async def _download_attachment(
    url: str,
    media_type: str,
    source_id: str,
    published_at: datetime,
    index: int,
    download_root: Path,
    prefix: str
) -> Optional[str]:
    """
    下载单个附件并返回相对路径

    Args:
        url: 媒体文件URL
        media_type: 媒体类型（"image" 或 "video"）
        source_id: 来源ID
        published_at: 发布时间
        index: 附件索引
        download_root: 下载根目录
        prefix: 文件名前缀

    Returns:
        相对路径，如 "2026-02-23/images/zhihu_xxx_0_a1b2c3d4.jpg"
        下载失败返回 None
    """
    url = (url or "").strip()
    if not url:
        return None

    # 1. 构建目标路径
    date_folder = published_at.astimezone(timezone.utc).strftime("%Y-%m-%d")
    subdir = "images" if media_type == "image" else "videos"
    target_dir = download_root / date_folder / subdir
    target_dir.mkdir(parents=True, exist_ok=True)

    # 2. 生成文件名
    source_id_short = _safe_name(source_id, fallback="noid")[:24]
    url_hash8 = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]

    # 3. 下载文件并获取扩展名
    timeout = aiohttp.ClientTimeout(total=None)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.zhihu.com/",
    }

    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.read()
                content_type = response.headers.get("Content-Type", "")

        # 确定文件扩展名
        ext = _get_extension_from_url(url)
        if not ext:
            ext = _get_extension_from_content_type(content_type, media_type)

        # 生成完整文件名
        file_name = f"{prefix}_{source_id_short}_{index}_{url_hash8}{ext}"
        target_path = target_dir / file_name

        # 保存文件
        with open(target_path, "wb") as f:
            f.write(data)

        # 返回相对路径
        relative_path = target_path.relative_to(download_root).as_posix()
        return relative_path

    except Exception as e:
        print(f"[WARN] Download attachment failed: {url} -> {type(e).__name__}: {e!r}")
        return None


def _replace_media_with_placeholders(body: str, attachments: List[Attachment]) -> str:
    """
    将body中的媒体标签替换为<attach_n>占位符

    注意：这个函数假设body可能包含HTML标签
    如果body是纯文本，则不做替换

    Args:
        body: 原始body文本（可能包含HTML）
        attachments: 附件列表

    Returns:
        替换后的body文本
    """
    if not body or not attachments:
        return body

    # 检查body是否包含HTML标签
    if not ("<img" in body or "<video" in body):
        # 纯文本，不需要替换
        return body

    # 解析HTML
    soup = BeautifulSoup(body, "html.parser")
    media_tags = soup.find_all(["img", "video"])

    # 为每个媒体标签创建占位符
    for idx, tag in enumerate(media_tags):
        if idx < len(attachments):
            placeholder = f"<attach_{idx}>"
            tag.replace_with(placeholder)

    # 返回处理后的文本
    result = soup.get_text("\n", strip=True)
    result = re.sub(r"\n{2,}", "\n", result).strip()
    return result


def _safe_name(value: str, fallback: str = "unknown") -> str:
    """
    清理字符串为安全的文件名

    Args:
        value: 原始字符串
        fallback: 如果value为空，使用的默认值

    Returns:
        安全的文件名字符串
    """
    text = (value or "").strip()
    if not text:
        return fallback
    text = re.sub(r"[^A-Za-z0-9_-]+", "_", text)
    return text[:64] if text else fallback


def _get_extension_from_url(url: str) -> str:
    """
    从URL中提取文件扩展名

    Args:
        url: 媒体文件URL

    Returns:
        文件扩展名（包含点号），如 ".jpg"
        如果无法提取则返回空字符串
    """
    try:
        path = urlparse(url).path or ""
        ext = os.path.splitext(path)[1].lower()
        if ext and len(ext) <= 8:
            return ext
    except Exception:
        pass
    return ""


def _get_extension_from_content_type(content_type: str, media_type: str) -> str:
    """
    根据Content-Type确定文件扩展名

    Args:
        content_type: HTTP响应的Content-Type头
        media_type: 媒体类型（"image" 或 "video"）

    Returns:
        文件扩展名（包含点号），如 ".jpg"
    """
    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/bmp": ".bmp",
        "video/mp4": ".mp4",
        "video/webm": ".webm",
        "video/quicktime": ".mov",
        "video/x-msvideo": ".avi",
        "video/x-matroska": ".mkv",
    }
    ext = mapping.get((content_type or "").split(";")[0].strip().lower())
    if ext:
        return ext
    return ".jpg" if media_type == "image" else ".mp4"
