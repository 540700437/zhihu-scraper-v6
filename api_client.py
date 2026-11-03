import re
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List, Optional, Dict

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import Answer, Image
from .utils import html_to_text
from .logger import logger


class ZhihuAPIClient:
    def __init__(self, page, limit: int = 20, concurrency: int = 5):
        self.page = page
        self.limit = limit
        self.concurrency = concurrency
        self._cookies: Optional[Dict[str, str]] = None

        self.session = requests.Session()
        retries = Retry(
            total=2,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(
            max_retries=retries, pool_connections=10, pool_maxsize=20
        )
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _get_cookies(self) -> Dict[str, str]:
        if self._cookies is None:
            raw = self.page.context.cookies("https://www.zhihu.com")
            self._cookies = {c["name"]: c["value"] for c in raw if c.get("value")}
        return self._cookies

    def _fetch_page(self, question_id: str, offset: int) -> dict:
        cookies = self._get_cookies()
        # 🔥 使用安全的 include 字段，只包含官方支持的字段
        include_fields = (
            "data%5B%2A%5D.is_normal%2Ccontent%2C"
            "voteup_count%2Cfavorite_count%2Cfav_count%2Ccollect_count%2C"
            "comment_count%2Ccreated_time%2Cupdated_time%2Cauthor%2C"
            "stat"  # stat 对象可能包含收藏相关字段
        )
        url = (
            f"https://www.zhihu.com/api/v4/questions/{question_id}/answers"
            f"?include={include_fields}"
            f"&offset={offset}&limit={self.limit}&sort_by=default"
        )
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": f"https://www.zhihu.com/question/{question_id}",
            "Accept": "application/json, text/plain, */*",
        }

        time.sleep(random.uniform(0.5, 1.5))
        resp = self.session.get(url, cookies=cookies, headers=headers, timeout=(10, 25))
        if resp.status_code == 429:
            raise RuntimeError("Rate limited by Zhihu API")
        resp.raise_for_status()
        return resp.json()

    def fetch_all(self, question_id: str, start_offset: int = 0) -> List[Answer]:
        logger.info("API: 开始并发抓取 question=%s", question_id)

        first_data = self._fetch_page(question_id, start_offset)
        paging = first_data.get("paging", {})
        totals = paging.get("totals", 0)
        is_end = paging.get("is_end", True)

        all_items = first_data.get("data", [])
        answers = [self._parse_item(item, question_id) for item in all_items]
        answers = [a for a in answers if a]

        if is_end or not totals:
            logger.info("API: 仅 %d 条，无需分页", len(answers))
            return answers

        offsets = list(range(start_offset + self.limit, totals, self.limit))
        logger.info("API: 预估总量 %d，将并发请求 %d 页", totals, len(offsets))

        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            future_to_offset = {
                executor.submit(self._fetch_page, question_id, off): off
                for off in offsets
            }

            for future in as_completed(future_to_offset):
                offset = future_to_offset[future]
                try:
                    data = future.result(timeout=60)
                    batch = [
                        self._parse_item(item, question_id)
                        for item in data.get("data", [])
                    ]
                    batch = [a for a in batch if a]
                    answers.extend(batch)
                    logger.info(
                        "API: offset=%d 完成，本批 %d 条，累计 %d 条",
                        offset,
                        len(batch),
                        len(answers),
                    )
                except Exception as e:
                    logger.error("API: offset=%d 失败: %s", offset, e)
                time.sleep(random.uniform(0.3, 0.8))

        logger.info("API: 抓取完成，共 %d 条", len(answers))
        return answers

    def _parse_item(self, item: dict, question_id: str) -> Optional[Answer]:
        try:
            author_info = item.get("author") or {}
            author_name = author_info.get("name") or "匿名用户"
            author_id = author_info.get("url_token") or author_info.get("id")

            vote_count = item.get("voteup_count", 0) or 0
            comment_count = item.get("comment_count", 0) or 0

            # ========== 收藏数提取 ==========
            favorite_count = self._extract_favorite_count(item)

            created_ts = item.get("created_time", 0)
            updated_ts = item.get("updated_time", 0)
            created_time = datetime.fromtimestamp(created_ts) if created_ts else None
            updated_time = datetime.fromtimestamp(updated_ts) if updated_ts else None

            qid = item.get("question", {}).get("id", question_id)
            aid = item.get("id", "")
            link = item.get("url") or f"https://www.zhihu.com/question/{qid}/answer/{aid}"

            content_html = item.get("content", "") or ""
            content_text = html_to_text(content_html)

            images = []
            seen = set()
            for url in re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', content_html):
                if url.startswith("//"):
                    url = "https:" + url
                if url not in seen and url.startswith("http"):
                    seen.add(url)
                    images.append(Image(image_url=url))

            code_blocks = []
            for pre_match in re.findall(r'<pre[^>]*>(.*?)</pre>', content_html, re.DOTALL):
                code_text = re.sub(r'<[^>]+>', "", pre_match)
                code_text = __import__("html").unescape(code_text).strip()
                if code_text:
                    code_blocks.append(code_text)

            has_video = "<video" in content_html or "VideoAnswerPlayer" in content_html

            return Answer(
                answer_id=str(aid),
                question_id=str(qid),
                author_id=str(author_id) if author_id else None,
                author_name=author_name,
                vote_count=vote_count,
                favorite_count=favorite_count,
                comment_count=comment_count,
                content=content_text,
                content_html=content_html[:50000],
                created_time=created_time,
                updated_time=updated_time,
                link=link,
                images=images,
                code_blocks=code_blocks,
                has_video=has_video,
                source="API",
            )
        except Exception as e:
            logger.exception("API parse item failed: %s", e)
            return None

    def _extract_favorite_count(self, item: dict) -> int:
        """
        从 API 返回的 JSON 中提取收藏数，尝试多个可能的字段路径。
        """
        # 1. 顶层直接字段
        direct_keys = [
            "favorite_count",
            "fav_count",
            "collect_count",
            "collected_count",
            "favorited_count",
            "star_count",
            "bookmark_count",
        ]
        for key in direct_keys:
            val = item.get(key)
            if val is not None:
                try:
                    return int(val)
                except:
                    pass

        # 2. stat 嵌套
        stat = item.get("stat")
        if stat and isinstance(stat, dict):
            for key in direct_keys:
                val = stat.get(key)
                if val is not None:
                    try:
                        return int(val)
                    except:
                        pass

        # 3. 从 content 文本提取（最后的兜底）
        content = item.get("content", "")
        if content:
            match = re.search(r"收藏[：:]\s*(\d+)", content)
            if match:
                return int(match.group(1))

        return 0