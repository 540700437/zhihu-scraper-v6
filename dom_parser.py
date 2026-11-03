import re
import json
from datetime import datetime
from typing import List, Optional
from bs4 import BeautifulSoup, Tag
from .models import Answer, Image
from .selectors import SelectorManager
from .utils import clean_vote_count, clean_favorite_count, html_to_text
from .logger import logger


class DOMExtractor:
    def __init__(self, selector_manager: SelectorManager, page=None):
        self.sm = selector_manager
        self.page = page

    def extract(self, html: str, question_id: str) -> List[Answer]:
        soup = BeautifulSoup(html, "lxml")
        answers = []

        item_sel = self.sm.select(soup, "answer_item")
        if not item_sel:
            logger.error("DOM: 无法定位回答项")
            return []

        items = soup.select(item_sel)
        logger.info("DOM: 命中 %d 个回答项", len(items))

        # 先用 BeautifulSoup 解析常规字段（点赞、作者、时间等）
        for item in items:
            ans = self._parse_item(item, question_id)
            if ans:
                answers.append(ans)

        # ========== 强制用 JS 覆盖收藏数 ==========
        if self.page:
            logger.info("🔄 正在用 JS 精准提取收藏数...")
            js_map = self._js_extract_favorites()
            if js_map:
                updated = 0
                for ans in answers:
                    if ans.answer_id in js_map:
                        new_val = js_map[ans.answer_id]
                        if new_val != ans.favorite_count:
                            ans.favorite_count = new_val
                            updated += 1
                logger.info("✅ JS 更新了 %d 个回答的收藏数", updated)
                # 直接打印到控制台，方便查看
                sample = [a for a in answers if a.favorite_count > 0][:5]
                if sample:
                    print("\n📊 成功提取到收藏数（示例）：")
                    for a in sample:
                        print(f"  回答 {a.answer_id} 收藏数: {a.favorite_count}")
                else:
                    print("\n⚠️ 未提取到任何大于 0 的收藏数，可能页面未显示数字。")
            else:
                logger.warning("⚠️ JS 未能提取到任何收藏数")
        else:
            logger.warning("⚠️ 没有 page 对象，无法执行 JS 提取")

        return answers

    def _js_extract_favorites(self) -> dict:
        """
        在浏览器中执行 JavaScript，精准定位收藏按钮，提取数字。
        """
        try:
            result = self.page.evaluate("""() => {
                const map = {};
                // 先获取所有回答卡片
                const items = document.querySelectorAll('.List-item, .Card.AnswerCard, [data-za-detail-view-element_name*="Answer"]');
                items.forEach(el => {
                    let aid = null;
                    const zop = el.getAttribute('data-zop');
                    if (zop) {
                        try { aid = JSON.parse(zop).itemId; } catch(e) {}
                    }
                    if (!aid) {
                        const link = el.querySelector('a[href*="/answer/"]');
                        if (link) {
                            const m = link.href.match(/\\/answer\\/(\\d+)/);
                            if (m) aid = m[1];
                        }
                    }
                    if (!aid) return;

                    // 精准定位：收藏按钮（根据你提供的 HTML 结构）
                    let fav = 0;
                    // 方法1：精确匹配 class 和 aria-label
                    const btn = el.querySelector('button.Button.ContentItem-action[aria-label="收藏"]');
                    if (btn) {
                        // 提取按钮的纯文本（数字）
                        const text = btn.innerText || btn.textContent || '';
                        const m = text.match(/(\\d+)/);
                        if (m) fav = parseInt(m[1]);
                    }
                    // 方法2：如果没找到，尝试所有 aria-label="收藏" 的元素
                    if (fav === 0) {
                        const nodes = el.querySelectorAll('[aria-label="收藏"]');
                        for (let node of nodes) {
                            const text = node.innerText || node.textContent || '';
                            const m = text.match(/(\\d+)/);
                            if (m) { fav = parseInt(m[1]); break; }
                        }
                    }
                    // 方法3：如果还没找到，在包含 "收藏" 文本的元素中找数字
                    if (fav === 0) {
                        const all = el.querySelectorAll('*');
                        for (let node of all) {
                            const text = node.innerText || node.textContent || '';
                            if (text.includes('收藏')) {
                                const m = text.match(/(\\d+)/);
                                if (m) { fav = parseInt(m[1]); break; }
                            }
                        }
                    }
                    if (fav > 0) {
                        map[aid] = fav;
                    }
                });
                return map;
            }""")
            if result:
                print(f"\n📊 JS 提取到 {len(result)} 个收藏数")
                for k, v in list(result.items())[:3]:
                    print(f"  回答 {k} 收藏数: {v}")
            return result
        except Exception as e:
            logger.error("JS 执行失败: %s", e)
            return {}

    def _parse_item(self, item: Tag, question_id: str) -> Optional[Answer]:
        answer_id = self._extract_answer_id(item)
        if not answer_id:
            return None

        content_sel = self.sm.select(item, "rich_content")
        content_el = item.select_one(content_sel) if content_sel else None
        if not content_el:
            return None

        content_html = str(content_el)
        content_text = html_to_text(content_html)
        if not content_text:
            return None

        author_name = "匿名用户"
        author_id = None
        author_sel = self.sm.select(item, "author_name")
        if author_sel:
            author_el = item.select_one(author_sel)
            if author_el:
                author_name = author_el.get_text(strip=True)
                author_id = self._extract_author_id(author_el)

        vote_text = ""
        vote_sel = self.sm.select(item, "vote_count")
        if vote_sel:
            vote_el = item.select_one(vote_sel)
            if vote_el:
                vote_text = vote_el.get_text(strip=True) or vote_el.get("aria-label", "")
        vote_count = clean_vote_count(vote_text)

        time_text = ""
        link = ""
        time_sel = self.sm.select(item, "answer_time")
        if time_sel:
            time_el = item.select_one(time_sel)
            if time_el:
                time_text = time_el.get_text(strip=True)
                link = time_el.get("href", "")
                if link.startswith("//"):
                    link = "https:" + link

        images = self._extract_images(content_el)

        code_blocks = []
        for pre in content_el.find_all("pre"):
            if pre.find_parent("blockquote"):
                continue
            code = pre.find("code")
            code_text = code.get_text(strip=True) if code else pre.get_text(strip=True)
            if code_text:
                code_blocks.append(code_text)

        has_video = bool(
            content_el.find(["video", "iframe", "object", "embed"])
            or content_el.select_one(".VideoAnswerPlayer, .RichText-video")
        )

        return Answer(
            answer_id=answer_id,
            question_id=question_id,
            author_id=author_id,
            author_name=author_name,
            vote_count=vote_count,
            favorite_count=0,  # 先填0，后面JS覆盖
            content=content_text,
            content_html=content_html[:50000],
            images=images,
            code_blocks=code_blocks,
            has_video=has_video,
            link=link,
            source="DOM",
        )

    def _extract_answer_id(self, item: Tag) -> Optional[str]:
        zop = item.get("data-zop")
        if zop:
            try:
                data = json.loads(zop)
                if "itemId" in data:
                    return str(data["itemId"])
            except Exception:
                pass

        link_el = item.select_one("a[href*='/answer/']")
        if link_el:
            href = link_el.get("href", "")
            m = re.search(r"/answer/(\d+)", href)
            if m:
                return m.group(1)

        aid = item.get("data-aid") or item.get("data-answer-id")
        if aid:
            return str(aid)

        return None

    def _extract_author_id(self, el: Tag) -> Optional[str]:
        href = el.get("href", "")
        m = re.search(r"/people/([^/?]+)", href)
        return m.group(1) if m else None

    def _extract_images(self, el: Tag) -> List[Image]:
        images = []
        seen = set()
        for img in el.find_all("img"):
            url = (
                img.get("data-original")
                or img.get("data-src")
                or img.get("data-actualsrc")
                or img.get("src")
            )
            if not url:
                srcset = img.get("srcset", "")
                if srcset:
                    url = srcset.split(",")[0].split()[0]
            if url and url.startswith("http") and url not in seen:
                seen.add(url)
                images.append(Image(image_url=url))
        return images