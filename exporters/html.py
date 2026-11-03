import html as html_module
import json
from pathlib import Path
from typing import Iterator, List, Dict
from bs4 import BeautifulSoup
from .base import BaseExporter
from ..logger import logger


class HTMLExporter(BaseExporter):
    def export(self, question_id: str, question_title: str,
               answer_stream: Iterator[dict], per_page: int = 50):
        rows = list(answer_stream)
        total = len(rows)
        if total == 0:
            logger.warning("HTML: 无数据可导出")
            return

        pages = (total + per_page - 1) // per_page
        title_e = html_module.escape(question_title)

        # 预计算全局答主索引
        global_author_index: List[Dict] = []
        for page_idx in range(pages):
            chunk = rows[page_idx * per_page : (page_idx + 1) * per_page]
            for idx, row in enumerate(chunk):
                global_author_index.append({
                    "name": str(row.get("author_name") or "匿名用户"),
                    "page": page_idx + 1,
                    "anchor": f"ans-{page_idx}-{idx}",
                    "votes": row.get("vote_count", 0) or 0,
                })

        for page_idx in range(pages):
            chunk = rows[page_idx * per_page : (page_idx + 1) * per_page]
            page_num = page_idx + 1
            page_toc = self._render_page_toc(chunk, page_idx)
            articles = [self._render_article(row, page_idx, idx) for idx, row in enumerate(chunk)]
            nav = self._render_nav(page_num, pages, total)

            author_index_json = json.dumps(global_author_index, ensure_ascii=False)

            doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title_e} - 第{page_num}页</title>
<style>
body{{max-width:800px;margin:0 auto;padding:20px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;line-height:1.6;color:#333;background:#fafafa}}
h1{{font-size:1.5em;border-bottom:2px solid #0066cc;padding-bottom:10px}}
#searchBox{{position:sticky;top:0;background:rgba(250,250,250,0.95);backdrop-filter:blur(8px);padding:12px 0;margin-bottom:12px;border-bottom:1px solid #e0e0e0;z-index:100}}
#authorSearch{{width:100%;padding:10px 14px;border:1px solid #ddd;border-radius:6px;font-size:14px;box-sizing:border-box}}
#authorSearch:focus{{outline:none;border-color:#0066cc}}
#searchResults{{max-height:200px;overflow-y:auto;background:#fff;border:1px solid #ddd;border-radius:6px;margin-top:4px;display:none;box-shadow:0 4px 12px rgba(0,0,0,0.1)}}
.search-item{{padding:8px 14px;cursor:pointer;border-bottom:1px solid #f0f0f0;font-size:13px}}
.search-item:hover{{background:#f0f7ff}}
.no-result{{display:none !important}}
.page-toc{{background:#fff;padding:10px 14px;margin-bottom:14px;border-radius:6px;border:1px solid #e8e8e8;font-size:13px}}
.page-toc strong{{color:#444;margin-right:6px}}
.page-toc a{{color:#0066cc;text-decoration:none;margin:0 6px;display:inline-block;padding:2px 0}}
.page-toc a:hover{{text-decoration:underline}}
article{{background:#fff;padding:16px 20px;margin-bottom:16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.08);scroll-margin-top:80px}}
.meta{{color:#666;font-size:0.9em;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #f0f0f0;display:flex;align-items:center;flex-wrap:wrap;gap:8px}}
.meta strong{{color:#222;font-size:1.05em;margin-right:4px}}
.meta .stats{{display:flex;gap:12px;font-size:0.85em;color:#555;margin-left:auto;flex-wrap:wrap}}
.meta .stats span{{background:#f5f5f5;padding:2px 8px;border-radius:12px;white-space:nowrap}}
.body{{color:#444}}
.body p{{margin:0.6em 0}}
.body img{{max-width:100%;height:auto;border-radius:4px;margin:4px 0;display:block}}
pre{{background:#f6f8fa;padding:12px;border-radius:6px;overflow-x:auto;font-size:0.9em}}
pre code{{font-family:SFMono-Regular,Consolas,monospace}}
blockquote{{border-left:4px solid #dfe2e5;padding-left:16px;color:#6a737d;margin:0}}
a{{color:#0066cc}}
h2,h3,h4{{color:#222;margin-top:1.2em;margin-bottom:0.6em}}
details{{background:#f9f9f9;padding:10px;border-radius:4px;margin-top:8px}}
summary{{cursor:pointer;color:#0066cc;font-weight:500;user-select:none}}
.preview{{color:#666;margin-bottom:6px}}
nav{{position:sticky;bottom:0;background:rgba(255,255,255,0.95);backdrop-filter:blur(8px);padding:12px 20px;margin:20px -20px -20px;border-top:1px solid #e0e0e0;display:flex;justify-content:space-between;align-items:center;box-shadow:0 -2px 8px rgba(0,0,0,0.05)}}
nav a{{color:#0066cc;text-decoration:none;font-weight:500;padding:6px 12px;border-radius:4px}}
nav a:hover{{background:#f0f7ff}}
</style>
</head>
<body>
<h1>{title_e}</h1>
<div id="searchBox">
  <input type="text" id="authorSearch" placeholder="🔍 搜索答主名字（全局模糊匹配，点击跳转）..." autocomplete="off">
  <div id="searchResults"></div>
</div>
{page_toc}
<div id="articleList">
{"".join(articles)}
</div>
<nav>{nav}</nav>
<script>
const AUTHOR_INDEX = {author_index_json};
const CURRENT_PAGE = {page_num};

document.addEventListener("DOMContentLoaded", function() {{
  const imgs = document.querySelectorAll('img[data-src]');
  const obs = new IntersectionObserver(function(entries) {{
    entries.forEach(function(e) {{
      if(e.isIntersecting) {{
        const i = e.target;
        i.src = i.dataset.src;
        i.removeAttribute('data-src');
        obs.unobserve(i);
      }}
    }});
  }});
  imgs.forEach(function(i) {{ obs.observe(i); }});

  const input = document.getElementById('authorSearch');
  const results = document.getElementById('searchResults');
  
  input.addEventListener('input', function(e) {{
    const term = e.target.value.trim().toLowerCase();
    if(!term) {{
      results.style.display = 'none';
      results.innerHTML = '';
      filterCurrentPage('');
      return;
    }}
    
    const matches = AUTHOR_INDEX.filter(function(a) {{
      return a.name.toLowerCase().includes(term);
    }});
    
    if(matches.length === 0) {{
      results.innerHTML = '<div class="search-item">无匹配结果</div>';
      results.style.display = 'block';
      filterCurrentPage(term);
      return;
    }}
    
    const seen = new Set();
    const htmlParts = [];
    for(let i = 0; i < matches.length; i++) {{
      const m = matches[i];
      const key = m.name + '-' + m.page;
      if(seen.has(key)) continue;
      seen.add(key);
      const isCurrentPage = (m.page === CURRENT_PAGE);
      const target = isCurrentPage ? ('#' + m.anchor) : ('page_' + String(m.page).padStart(3, '0') + '.html#' + m.anchor);
      const badge = isCurrentPage ? '<span style="color:green">[本页]</span>' : ('<span style="color:#999">第' + m.page + '页</span>');
      htmlParts.push('<div class="search-item" onclick="window.location.href=\\'' + target + '\\'"><strong>' + m.name + '</strong> ' + badge + ' 👍' + m.votes + '</div>');
    }}
    
    results.innerHTML = htmlParts.join('') || '<div class="search-item">无匹配结果</div>';
    results.style.display = 'block';
    filterCurrentPage(term);
  }});
  
  document.addEventListener('click', function(e) {{
    if(!document.getElementById('searchBox').contains(e.target)) {{
      results.style.display = 'none';
    }}
  }});
  
  function filterCurrentPage(term) {{
    const articles = document.querySelectorAll('#articleList article');
    articles.forEach(function(art) {{
      const authorEl = art.querySelector('.meta strong');
      const author = authorEl ? authorEl.textContent.toLowerCase() : '';
      if(!term || author.includes(term)) {{
        art.classList.remove('no-result');
      }} else {{
        art.classList.add('no-result');
      }}
    }});
  }}
  
  if(location.hash) {{
    const el = document.querySelector(location.hash);
    if(el) setTimeout(function() {{ el.scrollIntoView({{behavior:'smooth', block:'start'}}); }}, 300);
  }}
}});
</script>
</body>
</html>"""

            html_path = self.output_dir / f"page_{page_num:03d}.html"
            html_path.write_text(doc, encoding="utf-8")

        self._write_index(title_e, pages, total, per_page)
        logger.info("HTML 导出完成: %s, 共 %d 条, %d 页", self.output_dir, total, pages)

    def _render_page_toc(self, chunk: List[dict], page_idx: int) -> str:
        if not chunk:
            return ""
        links = []
        for idx, row in enumerate(chunk):
            author = html_module.escape(str(row.get("author_name") or "匿名"))
            anchor = f"ans-{page_idx}-{idx}"
            links.append(f'<a href="#{anchor}">{author}</a>')
        return f'<div class="page-toc"><strong>📑 本页答主：</strong>{" · ".join(links)}</div>'

    def _sanitize_html(self, html: str) -> str:
        if not html:
            return ""
        soup = BeautifulSoup(html, "lxml")
        for tag in soup.find_all(["script", "style", "iframe", "frame", "object", "embed", "form"]):
            tag.decompose()
        for img in soup.find_all("img"):
            src = (img.get("data-original") or img.get("data-src") or 
                   img.get("data-actualsrc") or img.get("src"))
            if src:
                if src.startswith("//"):
                    src = "https:" + src
                img["data-src"] = src
                img["src"] = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
                img["loading"] = "lazy"
                img["style"] = "max-width:100%;height:auto;border-radius:4px;margin:4px 0;display:block;"
                img["onerror"] = "this.style.display='none'"
            else:
                img.decompose()
        for a in soup.find_all("a"):
            href = a.get("href", "")
            if href.startswith("//"):
                a["href"] = "https:" + href
            a["target"] = "_blank"
            a["rel"] = "noopener noreferrer"
        for pre in soup.find_all("pre"):
            pre["style"] = "background:#f6f8fa;padding:12px;border-radius:6px;overflow-x:auto;font-size:0.9em;"
            code = pre.find("code")
            if code:
                code["style"] = "font-family:SFMono-Regular,Consolas,monospace;"
        return str(soup)

    def _render_article(self, row: dict, page_idx: int, idx: int) -> str:
        author = html_module.escape(str(row.get("author_name") or "匿名用户"))
        votes = row.get("vote_count") or 0
        favs = row.get("favorite_count") or 0
        cmt = row.get("comment_count") or 0

        # 格式化大数字（如 102000 -> 102,000）
        def format_num(n):
            try:
                return f"{int(n):,}"
            except:
                return str(n)

        atime_raw = (row.get("updated_time") or row.get("created_time") or row.get("first_seen") or "")
        atime = str(atime_raw).split(".")[0]

        link = row.get("link", "")
        qid = row.get("question_id", "")
        aid = row.get("answer_id", "")
        if not link and qid and aid:
            link = f"https://www.zhihu.com/question/{qid}/answer/{aid}"
        link_e = html_module.escape(str(link))

        has_video = bool(row.get("has_video", 0))
        video_badge = " 🎬" if has_video else ""

        content_html_raw = row.get("content_html", "")
        if content_html_raw:
            full_body = self._sanitize_html(content_html_raw)
            text_preview = str(row.get("content") or "")[:200]
        else:
            text_preview = str(row.get("content") or "")
            full_body = html_module.escape(text_preview).replace("\n", "<br>")

        text_len = len(str(row.get("content") or ""))
        if text_len > 400:
            preview = html_module.escape(text_preview[:200])
            if len(preview) >= 200:
                preview += "..."
            body = f'''<div class="preview">{preview}</div>
<details id="detail-{page_idx}-{idx}">
  <summary>展开全文（共 {text_len} 字）</summary>
  <div style="margin-top:10px;">{full_body}</div>
</details>'''
        else:
            body = f"<div>{full_body}</div>"

        link_tag = f'<a href="{link_e}" target="_blank" style="margin-left:8px;">原文</a>' if link_e else ''

        # 🔥 统计信息卡片（赞同、收藏、评论、时间、原文链接）
        stats = f'''
        <div class="stats">
            <span>👍 {format_num(votes)}</span>
            <span>⭐ {format_num(favs)}</span>
            <span>💬 {format_num(cmt)}</span>
            <span>🕒 {atime}</span>
            {link_tag}
        </div>
        '''

        return f"""<article id="ans-{page_idx}-{idx}">
<div class="meta">
    <strong>{author}</strong>{video_badge}
    {stats}
</div>
<div class="body">{body}</div>
</article>"""

    def _render_nav(self, page_num: int, pages: int, total: int) -> str:
        parts = []
        parts.append(f'<a href="index.html" style="font-weight:bold;">📚 返回目录</a>')
        parts.append(f'<span>第 {page_num}/{pages} 页（共 {total} 条）</span>')
        if page_num > 1:
            parts.insert(1, f'<a href="page_{page_num-1:03d}.html">← 上一页</a>')
        if page_num < pages:
            parts.append(f'<a href="page_{page_num+1:03d}.html">下一页 →</a>')
        return '　'.join(parts)

    def _write_index(self, title: str, pages: int, total: int, per_page: int):
        links = "\n".join([
            f'<li><a href="page_{i+1:03d}.html">第 {i+1} 页（{min((i+1)*per_page, total)} 条）</a></li>'
            for i in range(pages)
        ])
        html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>{title}</title><style>body{{max-width:600px;margin:50px auto;font-family:system-ui}}
h1{{color:#222}}ul{{line-height:2}}a{{color:#0066cc}}</style></head>
<body><h1>{title}</h1><p>共 {total} 条回答，分为 {pages} 页</p><ul>{links}</ul></body></html>"""
        (self.output_dir / "index.html").write_text(html, encoding="utf-8")