import re
import html as html_module
from typing import Optional


def clean_vote_count(text: Optional[str]) -> int:
    if not text:
        return 0
    text = str(text).replace("赞同", "").replace("▲", "").replace("▼", "")\
                    .replace(",", "").replace(" ", "").strip()
    if not text:
        return 0
    match = re.search(r"([\d.]+)\s*(万|w)?", text, re.IGNORECASE)
    if not match:
        return 0
    num_str, unit = match.group(1), match.group(2)
    try:
        num = float(num_str)
    except ValueError:
        return 0
    if unit:
        num *= 10000
    return int(num)


def clean_favorite_count(text: Optional[str]) -> int:
    if not text:
        return 0
    text = str(text).replace("收藏", "").replace(" ", "").strip()
    match = re.search(r"([\d.]+)\s*(万)?", text)
    if not match:
        return 0
    num = float(match.group(1))
    if match.group(2):
        num *= 10000
    return int(num)


def html_to_text(html: str) -> str:
    """高性能文本提取（优先 selectolax，回退 bs4）"""
    try:
        from selectolax.parser import HTMLParser
        tree = HTMLParser(html)
        return tree.body.text(separator="\n") if tree.body else ""
    except ImportError:
        pass
    
    text = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</div>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = html_module.unescape(text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def extract_question_id(url: str) -> Optional[str]:
    m = re.search(r"/question/(\d+)", url)
    return m.group(1) if m else None
