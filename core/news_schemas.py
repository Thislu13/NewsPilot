#
# Author: WangQiushuo 185886867@qq.com
# Date: 2025-12-18 21:15:42
# LastEditors: WangQiushuo 185886867@qq.com
# LastEditTime: 2026-04-04 14:40:30
# FilePath: \NewsPilot\core\news_schemas.py
# Description: 新闻数据结构 Pydantic 模型定义
# 
# Copyright (c) 2026 by , All Rights Reserved. 
from pydantic import BaseModel, Field, HttpUrl, field_validator
from enum import Enum
from typing import List, Optional, Dict, Any

from datetime import datetime

class Attachment(BaseModel):
    """
    附件（如图片、视频、图表等）的结构。
    """
    type: str = Field(..., description="附件类型：image, video, chart, etc.")
    url: str = Field(..., description="附件的原始链接。")
    caption: Optional[str] = Field(None, description="附件的文字说明或图注。")
    file_id: Optional[str] = Field(None, description="如果已下载到本地存储，对应的文件ID/路径。")


class NewsItemRefinedSchema(BaseModel):
    '''
    精炼后的新闻内容格式。
    该格式作为模型的预备输入，去除冗余信息，仅保留核心内容和元数据。
    '''

    # --- 核心标识符与时间 ---

    unique_id: str = Field(..., description="系统内部生成的唯一标识符（UUID）。")
    source_id: str = Field(..., description="新闻源的唯一标识符（例如：'bloomberg_12345', 'reuters_xyz'）。")

    # --- 溯源信息 ---

    source_channel: str = Field(..., description="新闻来源渠道名称（例如：'Bloomberg', 'Reuters API', 'Local Scraper'）。")
    source_url: str = Field(..., description="新闻的原始网页或API地址。")
    NewsItemRaw_id: str = Field(..., description="指向 SupportingDocumentSchema 的链接ID。用于追溯到原始新闻内容。")

    # --- 时间信息 ---

    published_at: datetime = Field(..., description="新闻的发布时间（UTC/带时区）。")
    fetched_at: datetime = Field(default_factory=datetime.now, description="系统抓取并存入数据库的时间（UTC）。")

    # --- 内容主体 ---

    title: str = Field(..., description="新闻标题。")
    abstract: Optional[str] = Field(None, description="新闻精炼后内容。")

    # --- 关键元数据 ---
    categories: List[str] = Field(default_factory=list, description="新闻分类标签（例如：'Finance', 'Technology', 'Macro'）。")

    # --- LLM 评估和编码 ---
    # embedding: Optional[List[float]] = Field(None, description="新闻内容的向量化表示（Embedding），用于语义去重或检索。")
    evaluation_score: Optional[float] = Field(None, description="经模型评估的新闻可信度/重要性评分（0-100）。")

    # --- 扩展字段 ---
    
    extra_data: Optional[Dict[str, Any]] = Field(None, description="用于存储特定新闻源独有的、未被通用字段捕获的数据。")


class SupportingDocumentSchema(BaseModel):
    '''
    支持性文档的结构。
    用于存储与新闻相关的政策文件、报告等支持性材料。
    '''

    # --- 核心标识符与时间 ---

    unique_id: str = Field(..., description="系统内部生成的唯一标识符（UUID）。")
    
    # -- 溯源信息 ---

    source_channel: str = Field(..., description="支持性文档的来源渠道名称（例如：'政府官网', '官方报告库'）。")
    source_url: str = Field(..., description="支持性文档的原始网页或下载地址。")

    # --- 时间信息 ---

    published_at: datetime = Field(..., description="支持性文档的发布时间（UTC/带时区）。")
    fetched_at: datetime = Field(default_factory=datetime.now, description="系统抓取并存入数据库的时间（UTC）。")

    # --- 内容主体 ---

    title: str = Field(..., description="支持性文档的标题。")
    abstract: Optional[str] = Field(None, description="支持性文档的摘要或导语。")
    body: str = Field(..., description="支持性文档的主体内容（相对完整）。")

    # -- 关键元数据 ---

    document_type: Optional[str] = Field(None, description="支持性文档的类型（例如：'政策文件', '经济报告'）。")

    # -- 附件与关联文件 ---

    attachments: List[Attachment] = Field(default_factory=list, description="新闻中的图片、视频等附件列表。")


class NewsItemRawSchema(BaseModel):
    """
    抓取到的相对完整的新闻内容格式。
    该格式用于存储在原始新闻数据库中。
    """
    
    # --- 核心标识符与时间 ---
    
    unique_id: str = Field(..., description="系统内部生成的唯一标识符（UUID）。")
    source_id: str = Field(..., description="新闻源的唯一标识符（例如：'bloomberg_12345', 'reuters_xyz'）。")
    
    # --- 溯源信息 ---
    
    source_channel: str = Field(..., description="新闻来源渠道名称（例如：'Bloomberg', 'Reuters API', 'Local Scraper'）。")
    source_url: str = Field(..., description="新闻的原始网页或API地址。")
    
    # --- 时间信息 ---
    
    published_at: datetime = Field(..., description="新闻的发布时间（UTC/带时区）。")
    fetched_at: datetime = Field(default_factory=datetime.now, description="系统抓取并存入数据库的时间（UTC）。")

    # --- 内容主体 ---
    
    title: str = Field(..., description="新闻标题。")
    abstract: Optional[str] = Field(None, description="新闻摘要或导语。")
    body: str = Field(..., description="新闻主体内容（相对完整）。")
    
    # --- 关键元数据 ---
    
    authors: List[str] = Field(default_factory=list, description="新闻的作者列表。")
    categories: List[str] = Field(default_factory=list, description="新闻分类标签（例如：'Finance', 'Technology', 'Macro'）。")
    
    # --- 附件与关联文件 ---
    
    attachments: List[Attachment] = Field(default_factory=list, description="新闻中的图片、视频等附件列表。")
    
    supportingDocument_id: List[str] = Field(default_factory=list, 
        description="指向 SupportingDocumentSchema 的链接ID。 如果新闻提及官方报告，该ID指向文档存储系统中的文件。")
    
    # --- LLM 评估  ---
        
    evaluation_score: Optional[float] = Field(None, description="经模型评估的新闻可信度/重要性评分（0-100）。")

    # --- 扩展字段 ---
    
    extra_data: Optional[Dict[str, Any]] = Field(None, description="用于存储特定新闻源独有的、未被通用字段捕获的数据。")