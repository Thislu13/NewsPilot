"""建图模块数据类"""
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


@dataclass
class EventItem:
    event_id: str
    source_news_id: str
    source_channel: str
    source_url: str
    categories: Optional[List[str]] = None
    event_text: str = ""
    embedding: Optional[List[float]] = None
    published_at: Optional[datetime] = None
    fetched_at: Optional[datetime] = None
    status: str = "pending"
    created_at: Optional[datetime] = None


@dataclass
class ClusterItem:
    cluster_id: str
    parent_cluster_id: Optional[str] = None
    centroid: Optional[List[float]] = None
    child_cluster_ids: List[str] = field(default_factory=list)
    depth: int = 0
    dirty: bool = True
    splittable: bool = True
    brief_description: str = ""
    detailed_description: str = ""
    weekly_description: str = ""
    recent_description: str = ""
    status: str = "active"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    description_updated_at: Optional[datetime] = None


@dataclass
class MembershipItem:
    event_id: str
    cluster_id: str
    sim_score: Optional[float] = None
    checked: bool = False
    created_at: Optional[datetime] = None


@dataclass
class ClusterGroup:
    events: List[EventItem]
    brief_description: str = ""
    detailed_description: str = ""
    weekly_description: str = ""
    recent_description: str = ""
    outlier_event_ids: List[str] = field(default_factory=list)
    centroid: Optional[List[float]] = None


@dataclass
class ClusterResult:
    groups: List[ClusterGroup]
    outlier_events: List[EventItem]
