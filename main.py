import argparse
import random
import time
import re
from datetime import datetime
from pathlib import Path
from typing import List

from playwright.sync_api import TimeoutError as PWTimeoutError

from .config import settings
from .logger import logger
from .database import Database
from .models import Question
from .selectors import SelectorManager
from .dom_parser import DOMExtractor
from .api_client import ZhihuAPIClient
from .scroll_manager import ScrollManager
from .browser import BrowserManager
from .utils import extract_question_id
from .exporters import (
    MarkdownExporter, HTMLExporter, JSONExporter,
    CSVExporter, ExcelExporter, ParquetExporter,
)


def parse_args():
    parser = argparse.ArgumentParser(description="知乎回答抓取器 v6")
    parser.add_argument("urls", nargs="*", help="知乎问题 URL")
    parser.add_argument("--url-file", type=str, help="URL 列表文件")
    parser.add_argument("--headless", action="store_true", help="无头模式")
    parser.add_argument("--export", nargs="+", default=["md", "html", "json"],
                       choices=["md", "html", "json", "csv", "excel", "parquet", "all"],
                       help="导出格式")
    parser.add_argument("--no-dom", action="store_true", help="跳过 DOM 抓取，只用 API")
    parser.add_argument("--no-api", action="store_true", help="跳过 API，只用 DOM")
    return parser.parse_args()


def resolve_urls(args) -> List[str]:
    urls = list(args.urls)
    if args.url_file:
        with open(args.url_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    urls.append(line)
    if not urls:
        urls = ["https://www.zhihu.com/question/28966967"]
    seen = set()
    return [u for u in urls if not (u in seen or seen.add(u))]


def scrape_single(browser_mgr: BrowserManager, db: Database, 
                  url: str, args, batch_id: str):
    question_id = extract_question_id(url)
    if not question_id:
        logger.error("无法从 URL 提取 question_id: %s", url)
        return

    logger.info("=" * 50)
    logger.info("开始抓取 [%s]", url)

    page = browser_mgr.page
    sm = SelectorManager()

    # 打开页面
    browser_mgr.goto(url)
    time.sleep(random.uniform(1.5, 2.5))

    # 获取标题
    title = _extract_title(page, sm)
    if not title:
        logger.error("无法获取问题标题")
        return

    logger.info("📌 问题: %s", title)

    # 保存/更新问题
    q = Question(
        question_id=question_id,
        title=title,
        url=page.url,
        status="active"
    )
    db.save_question(q)

    # 检查断点续爬
    progress = db.get_progress(question_id)
    start_offset = progress["current_offset"] if progress else 0

    # ========== Phase 1: DOM ==========
    dom_count = 0
    if not args.no_dom:
        logger.info("📄 Phase 1: DOM 抓取...")
        browser_mgr.ensure_login()

        scroll = ScrollManager(page, sm)
        scroll.run(min_answers=5, max_rounds=15)

        # 提取
        html_content = page.content()
        
        extractor = DOMExtractor(sm, page=browser_mgr.page)  # 传入 page
        dom_answers = extractor.extract(html_content, question_id)
        updated, total = db.save_answers(question_id, dom_answers, "DOM", batch_id)
        dom_count = len(dom_answers)
        logger.info("DOM 完成: 提取 %d 条, 更新 %d 条, 库中累计 %d 条", 
                   dom_count, updated, total)

       # ========== Phase 2: API ==========
    api_count = 0
    if not args.no_api:
        logger.info("📡 Phase 2: API 并发抓取...")
        client = ZhihuAPIClient(
            page, 
            limit=settings.api_limit,
            concurrency=settings.api_concurrency
        )
        api_answers = client.fetch_all(question_id, start_offset)

        updated, total = db.save_answers(question_id, api_answers, "API", batch_id)
        api_count = len(api_answers)
        logger.info("API 完成: 提取 %d 条, 更新 %d 条, 库中累计 %d 条",
                   api_count, updated, total)

        # 更新进度
        db.save_progress(question_id, offset=start_offset + api_count,
                        total=total, status="completed")

    # ========== 导出 ==========
    total_in_db = db.count_answers(question_id)
    logger.info("💾 库中累计 %d 条，开始导出...", total_in_db)

    export_dir = settings.export_dir / question_id
    export_dir.mkdir(parents=True, exist_ok=True)

    # 使用生成器避免内存爆炸
    answer_stream = db.get_answers_for_export(question_id)

    formats = args.export
    if "all" in formats:
        formats = ["md", "html", "json", "csv", "excel", "parquet"]

    if "md" in formats:
        MarkdownExporter(export_dir / "markdown").export(
            question_id, title, answer_stream, per_page=settings.md_per_page)
        answer_stream = db.get_answers_for_export(question_id)  # 重新获取

    if "html" in formats:
        HTMLExporter(export_dir / "html").export(
            question_id, title, answer_stream, per_page=settings.html_per_page)
        answer_stream = db.get_answers_for_export(question_id)

    if "json" in formats:
        JSONExporter(export_dir).export(question_id, title, answer_stream)
        answer_stream = db.get_answers_for_export(question_id)

    if "csv" in formats:
        CSVExporter(export_dir).export(question_id, title, answer_stream)
        answer_stream = db.get_answers_for_export(question_id)

    if "excel" in formats:
        ExcelExporter(export_dir).export(question_id, title, answer_stream)
        answer_stream = db.get_answers_for_export(question_id)

    if "parquet" in formats:
        ParquetExporter(export_dir).export(question_id, title, answer_stream)

    logger.info("✅ 全部完成: %s", export_dir)


def _extract_title(page, sm: SelectorManager) -> str:
    from playwright.sync_api import TimeoutError as PWTimeoutError
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            html = page.content()
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            sel = sm.select(soup, "question_title")
            if sel:
                el = soup.select_one(sel)
                if el:
                    return el.get_text(strip=True)
        except Exception:
            pass
        time.sleep(0.5)
    # fallback
    try:
        return page.title()
    except PWTimeoutError:
        return ""


def main():
    args = parse_args()
    urls = resolve_urls(args)
    
    if args.headless:
        settings.headless = True

    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    db = Database()

    with BrowserManager() as browser:
        for i, url in enumerate(urls, 1):
            try:
                scrape_single(browser, db, url, args, batch_id)
            except Exception as e:
                logger.exception("抓取失败 [%s]: %s", url, e)
                try:
                    browser.page.screenshot(path=f"error_{i}.png", full_page=True)
                except Exception:
                    pass
            if i < len(urls):
                time.sleep(random.uniform(3, 6))
        
        input("\n按 Enter 关闭浏览器...")


if __name__ == "__main__":
    main()
