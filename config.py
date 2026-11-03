from pathlib import Path
from pydantic_settings import BaseSettings
from typing import List

# 项目根目录：路径一律以这里为基准，不随启动时的工作目录变化
PROJECT_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    # 路径
    db_path: Path = PROJECT_DIR / "zhihu_v6.db"
    export_dir: Path = PROJECT_DIR / "exports"
    user_data_dir: Path = Path.home() / "zhihu_chrome_profile_v6"
    log_dir: Path = PROJECT_DIR / "logs"
    
    # 浏览器
    headless: bool = False
    viewport_pool: List[dict] = [
        {"width": 1280, "height": 800},
        {"width": 1366, "height": 768},
        {"width": 1440, "height": 900},
    ]
    
    # API
    api_limit: int = 20
    api_concurrency: int = 5
    api_max_retry: int = 3
    api_base_sleep: float = 1.0
    
    # 滚动
    scroll_max_rounds: int = 100
    scroll_wall_clock_timeout: int = 60
    scroll_no_change_threshold: int = 3
    
    # 风控
    block_policy: str = "wait"  # wait / notify / abort
    block_wait_timeout: int = 300
    
    # 存储
    store_content_html: bool = True
    content_html_max_chars: int = 50000
    
    # 导出
    md_per_page: int = 100
    html_per_page: int = 50
    
    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
