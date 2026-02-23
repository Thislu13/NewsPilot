from sqlalchemy import Column, String, Text, DateTime, JSON, ForeignKey, Float
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()



class RawNews(Base):
    """
    对应 NewsItemRawSchema
    抓取到的相对完整的新闻内容格式。
    """
    __tablename__ = 'raw_news'

    # --- 核心标识符与时间 ---
    unique_id = Column(String(36), primary_key=True)
    source_id = Column(Text, nullable=True)

    # --- 溯源信息 ---
    source_channel = Column(Text, nullable=False) # ex: Bloomberg
    source_url = Column(Text, unique=True, nullable=False, index=True) # 原始网页

    # --- 时间信息 ---
    published_at = Column(DateTime(timezone=True), nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())

    # --- 内容主体 ---
    title = Column(Text, nullable=False)
    abstract = Column(Text, nullable=True)
    body = Column(Text, nullable=True) # 对应 schema 中的 body

    # --- 关键元数据 ---
    authors = Column(JSON, nullable=True) 
    categories = Column(JSON, nullable=True)

    # --- 附件与关联文件 ---
    # 存储 List[Attachment] -> List[Dict]
    attachments = Column(JSON, nullable=True)
    
    # 指向 SupportingDocumentSchema 的 ID 列表. list[str]
    supporting_document_ids = Column(JSON, nullable=True) 

    # --- LLM 评估与去重元数据 ---
    evaluation_score = Column(Float, nullable=True)

    # --- 扩展字段 ---
    extra_data = Column(JSON, nullable=True)

    # 关联关系
    refined_ref = relationship("RefinedNews", back_populates="raw_ref", uselist=False)

    def __repr__(self):
        return f"<RawNews(unique_id={self.unique_id}, title={self.title})>"

class RawNewsStaging(Base):
    """
    抓取阶段的临时缓冲区表。
    结构与 RawNews 基本一致，用于解耦抓取和后续处理。
    Daemon 从这里读取 pending 任务，处理成功后归档到 RawNews 并生成 RefinedNews。
    """
    __tablename__ = 'raw_news_staging'

    # --- 核心标识符 ---
    unique_id = Column(String(36), primary_key=True)
    source_id = Column(Text, nullable=True)

    # --- 溯源信息 ---
    source_channel = Column(Text, nullable=False)
    source_url = Column(Text, unique=True, nullable=False, index=True) # 用于抓取去重

    # --- 时间信息 ---
    published_at = Column(DateTime(timezone=True), nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())

    # --- 内容主体 ---
    title = Column(Text, nullable=False)
    abstract = Column(Text, nullable=True)
    body = Column(Text, nullable=True)

    # --- 关键元数据 ---
    authors = Column(JSON, nullable=True)
    categories = Column(JSON, nullable=True)

    # --- 附件与关联文件 ---
    # 存储 List[Attachment] -> List[Dict]
    attachments = Column(JSON, nullable=True)
    
    # 指向 SupportingDocumentSchema 的 ID 列表. list[str]
    supporting_document_ids = Column(JSON, nullable=True)

    # --- 队列状态字段 ---
    # pending: 待处理, processing: 处理中, completed: 已归档, failed: 失败
    processing_status = Column(String(20), default='pending', index=True) 
    retry_count = Column(Float, default=0) # 这里偷懒复用一下类型，实际最好是 Integer
    last_error = Column(Text, nullable=True)

    # --- 扩展 ---
    extra_data = Column(JSON, nullable=True)

    def __repr__(self):
        return f"<RawNewsStaging(id={self.unique_id}, status={self.processing_status})>"



class RefinedNews(Base):
    """
    对应 NewsItemRefinedSchema
    精炼后的新闻内容格式。
    """
    __tablename__ = 'refined_news'

    # --- 核心标识符 ---
    unique_id = Column(String(36), primary_key=True)
    source_id = Column(Text, nullable=True)

    # --- 溯源信息 ---
    source_channel = Column(Text, nullable=False)
    source_url = Column(Text, nullable=False)
    
    # 对应 NewsItemRaw_id
    news_item_raw_id = Column(String(36), ForeignKey('raw_news.unique_id'), unique=True, nullable=False)

    # --- 时间信息 ---
    published_at = Column(DateTime(timezone=True), nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())

    # --- 内容主体 ---
    title = Column(Text, nullable=False)
    abstract = Column(Text, nullable=True) # 精炼后内容

    # --- 关键元数据 ---
    categories = Column(JSON, nullable=True)

    # --- LLM 评估和编码 ---
    evaluation_score = Column(Float, nullable=True)
    embedding = Column(JSON, nullable=True)

    # --- 扩展字段 ---
    extra_data = Column(JSON, nullable=True)

    # 反向关联
    raw_ref = relationship("RawNews", back_populates="refined_ref")

    def __repr__(self):
        return f"<RefinedNews(unique_id={self.unique_id}, raw_id={self.news_item_raw_id})>"


class SupportingDocument(Base):
    """
    对应 SupportingDocumentSchema
    支持性文档
    """
    __tablename__ = 'supporting_documents'

    unique_id = Column(String(36), primary_key=True)
    
    source_channel = Column(Text, nullable=False)
    source_url = Column(Text, unique=True, nullable=False)

    published_at = Column(DateTime(timezone=True), nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())

    title = Column(Text, nullable=False)
    abstract = Column(Text, nullable=True)
    body = Column(Text, nullable=False)

    document_type = Column(Text, nullable=True)
    
    attachments = Column(JSON, nullable=True)

    def __repr__(self):
        return f"<SupportingDocument(unique_id={self.unique_id}, title={self.title})>"


class ZhihuRawPost(Base):
    """
    知乎专用原始内容表（抓取结果）。
    与新闻主流程隔离，用于后续定向语义分析。
    """
    __tablename__ = 'zhihu_raw_posts'

    unique_id = Column(String(36), primary_key=True)
    source_id = Column(Text, nullable=True)

    source_channel = Column(Text, nullable=False, default='Zhihu')
    source_url = Column(Text, unique=True, nullable=False, index=True)

    author = Column(Text, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())

    title = Column(Text, nullable=False)
    body = Column(Text, nullable=True)

    categories = Column(JSON, nullable=True)
    attachments = Column(JSON, nullable=True)
    extra_data = Column(JSON, nullable=True)

    # 处理状态: pending / completed
    status = Column(String(20), default='pending', index=True)

    def __repr__(self):
        return f"<ZhihuRawPost(unique_id={self.unique_id}, title={self.title})>"
