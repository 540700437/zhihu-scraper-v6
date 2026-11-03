from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime
import hashlib


@dataclass
class Question:
    question_id: str
    title: str
    url: str
    answer_count: int = 0
    follower_count: int = 0
    created_at: Optional[datetime] = None
    first_seen: Optional[datetime] = None
    last_updated: Optional[datetime] = None
    last_scraped_offset: int = 0
    status: str = "pending"


@dataclass
class Image:
    image_url: str
    answer_id: Optional[str] = None
    local_path: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    file_size: Optional[int] = None
    md5_hash: Optional[str] = None


@dataclass
class Answer:
    answer_id: str              # 真正身份：知乎回答ID
    question_id: str
    author_id: Optional[str] = None
    author_name: str = "匿名用户"
    vote_count: int = 0
    favorite_count: int = 0
    comment_count: int = 0
    content: str = ""
    content_html: str = ""
    content_hash: str = ""        # MD5，用于快速判重
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None
    source: str = ""            # 'DOM' | 'API'
    first_seen: Optional[datetime] = None
    last_update: Optional[datetime] = None
    scrape_batch_id: str = ""
    images: List[Image] = field(default_factory=list)
    code_blocks: List[str] = field(default_factory=list)
    has_video: bool = False
    link: str = ""
    
    def __post_init__(self):
        if not self.content_hash and self.content:
            self.content_hash = hashlib.md5(
                self.content.encode("utf-8")
            ).hexdigest()[:16]
