"""
知乎回答抓取器 v6
================

核心设计原则：
    1. 页面改版，只需修改 selectors.py
    2. 数据只保存一份，answer_id 为主键
    3. API 永远比 DOM 优先
    4. 导出任何数量回答都不会卡

用法：
    from zhihu_scraper_v6 import main
    main()  # 或 python -m zhihu_scraper_v6.main <url>
"""

__version__ = "6.0.0"
__author__ = "刘羽志"

from .config import settings
from .database import Database
from .models import Answer, Question, Image
from .logger import logger

__all__ = [
    "settings",
    "Database",
    "Answer",
    "Question", 
    "Image",
    "logger",
    "__version__",
]
