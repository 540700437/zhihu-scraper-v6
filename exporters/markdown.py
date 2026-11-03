import re
import html
from pathlib import Path
from typing import Iterator
from .base import BaseExporter
from ..logger import logger


class MarkdownExporter(BaseExporter):
    def export(self, question_id: str, question_title: str,
               answer_stream: Iterator[dict], per_page: int = 100):
        rows = list(answer_stream)
        total = len(rows)
        if total == 0:
            logger.warning("Markdown: 无数据")
            return
        
        pages = (total + per_page - 1) // per_page
        safe_title = self._safe_filename(question_title)[:30]
        
        for page_idx in range(pages):
            chunk = rows[page_idx * per_page : (page_idx + 1) * per_page]
            page_num = page_idx + 1
            md_path = self.output_dir / f"{page_num:03d}_{safe_title}.md"
            
            lines = [
                f"# {question_title}",
                f"> 第 {page_num}/{pages} 页 | 共 {total} 条 | 按赞同数排序\n",
            ]
            
            for row in chunk:
                lines.extend(self._render_answer(row))
            
            # 分页导航
            nav = []
            if page_num > 1:
                prev = f"{page_num-1:03d}_{safe_title}.md"
                nav.append(f"[← 上一页]({prev})")
            nav.append(f"第 {page_num}/{pages} 页")
            if page_num < pages:
                nxt = f"{page_num+1:03d}_{safe_title}.md"
                nav.append(f"[下一页 →]({nxt})")
            
            lines.append("\n" + " | ".join(nav))
            md_path.write_text("\n".join(lines), encoding="utf-8")
        
        logger.info("Markdown 导出完成: %s, 共 %d 条", self.output_dir, total)
    
    def _render_answer(self, row: dict) -> list:
        lines = []
        author = row.get("author_name", "匿名用户")
        votes = row.get("vote_count", 0)
        favs = row.get("favorite_count", 0)
        atime = row.get("created_time", "")
        link = row.get("link", "")
        content = row.get("content", "")
        has_video = row.get("has_video", 0)
        
        lines.append(f"## {author}")
        lines.append(f"👍 **赞同**：{votes}　|　⭐ **收藏**：{favs}　|　🕒 {atime}")
        if link:
            lines.append(f"🔗 [查看原文]({link})")
        if has_video:
            lines.append("🎬 *(包含视频)*")
        lines.append("")
        
        if content:
            # 转义 Markdown 特殊字符
            safe = self._escape_md(content)
            lines.append(safe)
        
        # 代码块
        codes = row.get("code_blocks", "[]")
        if codes:
            import json
            try:
                code_list = json.loads(codes)
                if code_list:
                    lines.append("\n**代码片段：**")
                    for code in code_list:
                        lines.append(f"\n```\n{code}\n```")
            except Exception:
                pass
        
        lines.append("\n---\n")
        return lines
    
    def _escape_md(self, text: str) -> str:
        # 保护已有代码块
        # 转义行首 # > - * ` [ 等
        lines = []
        in_code = False
        for line in text.split("\n"):
            stripped = line.lstrip()
            if stripped.startswith("```"):
                in_code = not in_code
                lines.append(line)
                continue
            if in_code:
                lines.append(line)
                continue
            # 转义行首 Markdown 标记
            if stripped.startswith(("#", ">", "-", "*", "[", "`", "|")):
                line = "\\" + line
            lines.append(line)
        return "\n".join(lines)
    
    def _safe_filename(self, s: str) -> str:
        return re.sub(r'[\\/:*?"<>|]', "_", s)
