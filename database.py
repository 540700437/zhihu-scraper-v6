import sqlite3
import contextlib
from datetime import datetime
from typing import List, Optional, Tuple
from .models import Answer, Question, Image
from .config import settings
from .logger import logger


class Database:
    def __init__(self, db_path: str = str(settings.db_path)):
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_db(self):
        with contextlib.closing(self._connect()) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS questions (
                    question_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    answer_count INTEGER DEFAULT 0,
                    follower_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP,
                    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_scraped_offset INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending'
                );

                CREATE TABLE IF NOT EXISTS answers (
                    answer_id TEXT PRIMARY KEY,
                    question_id TEXT NOT NULL REFERENCES questions(question_id),
                    author_id TEXT,
                    author_name TEXT,
                    vote_count INTEGER DEFAULT 0,
                    favorite_count INTEGER DEFAULT 0,
                    comment_count INTEGER DEFAULT 0,
                    content TEXT,
                    content_html TEXT,
                    content_hash TEXT,
                    created_time TIMESTAMP,
                    updated_time TIMESTAMP,
                    source TEXT NOT NULL,
                    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    scrape_batch_id TEXT
                );

                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    answer_id TEXT NOT NULL REFERENCES answers(answer_id),
                    image_url TEXT NOT NULL,
                    local_path TEXT,
                    width INTEGER,
                    height INTEGER,
                    file_size INTEGER,
                    md5_hash TEXT UNIQUE,
                    downloaded_at TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS scrape_progress (
                    question_id TEXT PRIMARY KEY REFERENCES questions(question_id),
                    current_offset INTEGER DEFAULT 0,
                    total_expected INTEGER,
                    last_answer_time TIMESTAMP,
                    status TEXT DEFAULT 'running',
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_answers_question 
                    ON answers(question_id);
                CREATE INDEX IF NOT EXISTS idx_images_answer 
                    ON images(answer_id);
            """)
            conn.commit()
            logger.info("Database initialized: %s", self.db_path)

    # ---------- Questions ----------
    def save_question(self, q: Question):
        with contextlib.closing(self._connect()) as conn:
            conn.execute("""
                INSERT INTO questions (question_id, title, url, answer_count, 
                    follower_count, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(question_id) DO UPDATE SET
                    title=excluded.title,
                    answer_count=excluded.answer_count,
                    follower_count=excluded.follower_count,
                    last_updated=CURRENT_TIMESTAMP,
                    status=excluded.status
            """, (q.question_id, q.title, q.url, q.answer_count,
                  q.follower_count, q.created_at, q.status))
            conn.commit()

    def get_question(self, question_id: str) -> Optional[Question]:
        with contextlib.closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM questions WHERE question_id = ?", 
                (question_id,)
            ).fetchone()
            if not row:
                return None
            return Question(**{k: row[k] for k in row.keys()})

    # ---------- Answers ----------
    def get_answer(self, answer_id: str) -> Optional[Answer]:
        with contextlib.closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM answers WHERE answer_id = ?", (answer_id,)
            ).fetchone()
            if not row:
                return None
            data = {k: row[k] for k in row.keys()}
            data["images"] = self._get_images_for_answer(conn, answer_id)
            return Answer(**data)

    def _get_images_for_answer(self, conn, answer_id: str) -> List[Image]:
        import dataclasses
        rows = conn.execute(
            "SELECT * FROM images WHERE answer_id = ?", (answer_id,)
        ).fetchall()
        allowed_fields = {f.name for f in dataclasses.fields(Image)}
        return [
            Image(**{k: r[k] for k in r.keys() if k in allowed_fields})
            for r in rows
        ]

    def should_update(self, existing: Answer, incoming: Answer, source: str) -> bool:
        """UPSERT 决策引擎"""
        # 规则1: DOM -> API 直接覆盖（但收藏数除外，在 save_answers 中单独保护）
        if existing.source == "DOM" and source == "API":
            return True

        # 规则2: API -> API，基于时间戳防缓存
        if existing.source == "API" and source == "API":
            def _to_dt(val):
                if val is None:
                    return None
                if isinstance(val, datetime):
                    return val
                if isinstance(val, str):
                    try:
                        return datetime.strptime(val, "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        try:
                            return datetime.fromisoformat(val.replace(" ", "T"))
                        except Exception:
                            return None
                return None

            existing_time = _to_dt(existing.updated_time)
            incoming_time = _to_dt(incoming.updated_time)

            if incoming_time and existing_time:
                if incoming_time > existing_time:
                    if incoming.vote_count >= existing.vote_count:
                        return True

            if incoming.content_hash != existing.content_hash:
                if len(incoming.content) > len(existing.content or "") * 1.05:
                    return True

        return False

    # ---------- 🔥 核心修改：API 永远不覆盖收藏数 ----------
    def save_answers(self, question_id: str, answers: List[Answer], 
                     source: str, batch_id: str) -> Tuple[int, int]:
        """返回 (updated, total)"""
        seen_ids = set()
        unique_answers = []
        for ans in answers:
            if ans.answer_id and ans.answer_id not in seen_ids:
                seen_ids.add(ans.answer_id)
                unique_answers.append(ans)

        updated = 0
        with contextlib.closing(self._connect()) as conn:
            for ans in unique_answers:
                ans.source = source
                ans.scrape_batch_id = batch_id
                ans.last_update = datetime.now()

                existing = self.get_answer(ans.answer_id)
                if existing is None:
                    # 全新插入
                    try:
                        conn.execute("""
                            INSERT INTO answers (
                                answer_id, question_id, author_id, author_name,
                                vote_count, favorite_count, comment_count,
                                content, content_html, content_hash,
                                created_time, updated_time, source,
                                first_seen, last_update, scrape_batch_id
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            ans.answer_id, ans.question_id, ans.author_id, ans.author_name,
                            ans.vote_count, ans.favorite_count, ans.comment_count,
                            ans.content, ans.content_html, ans.content_hash,
                            ans.created_time, ans.updated_time, ans.source,
                            datetime.now(), ans.last_update, ans.scrape_batch_id
                        ))
                        for img in ans.images:
                            self._insert_image(conn, img, ans.answer_id)
                        updated += 1
                    except sqlite3.IntegrityError:
                        logger.warning("answer_id=%s 已存在，跳过插入", ans.answer_id)
                else:
                    # 已存在：是否应该更新
                    if self.should_update(existing, ans, source):
                        # ===== 🔥 核心保护：收藏数永不丢失 =====
                        final_fav = existing.favorite_count  # 默认保留原值
                        
                        # 如果新值 > 0，则使用新值（允许更新为正确的收藏数）
                        if ans.favorite_count > 0:
                            final_fav = ans.favorite_count
                            logger.debug("更新收藏数: %d -> %d", existing.favorite_count, final_fav)
                        # 如果新值为 0 且原值 > 0，保留原值（API 通常为 0）
                        elif ans.favorite_count == 0 and existing.favorite_count > 0:
                            final_fav = existing.favorite_count
                            logger.debug("API 保留收藏数 %d (原值) 而非覆盖为 0", final_fav)
                        # 如果原值为 0 且新值也为 0，保持 0
                        else:
                            final_fav = 0

                        conn.execute("""
                            UPDATE answers SET
                                author_id=?, author_name=?, vote_count=?,
                                favorite_count=?, comment_count=?, content=?,
                                content_html=?, content_hash=?, created_time=?,
                                updated_time=?, source=?, last_update=?,
                                scrape_batch_id=?
                            WHERE answer_id=?
                        """, (
                            ans.author_id, ans.author_name, ans.vote_count,
                            final_fav, ans.comment_count, ans.content,
                            ans.content_html, ans.content_hash, ans.created_time,
                            ans.updated_time, ans.source, ans.last_update,
                            ans.scrape_batch_id, ans.answer_id
                        ))
                        for img in ans.images:
                            self._insert_image(conn, img, ans.answer_id)
                        updated += 1

            conn.commit()

        total = self.count_answers(question_id)
        logger.info("保存完成：更新 %d 条，库中累计 %d 条", updated, total)
        return updated, total

    def _insert_image(self, conn, img: Image, answer_id: str):
        try:
            conn.execute("""
                INSERT OR IGNORE INTO images 
                (answer_id, image_url, local_path, width, height, file_size, md5_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (answer_id, img.image_url, img.local_path,
                  img.width, img.height, img.file_size, img.md5_hash))
        except sqlite3.IntegrityError:
            pass

    def count_answers(self, question_id: str) -> int:
        with contextlib.closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM answers WHERE question_id = ?",
                (question_id,)
            ).fetchone()
            return row[0] if row else 0

    # ---------- Progress ----------
    def get_progress(self, question_id: str) -> Optional[dict]:
        with contextlib.closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM scrape_progress WHERE question_id = ?",
                (question_id,)
            ).fetchone()
            return dict(row) if row else None

    def save_progress(self, question_id: str, offset: int, 
                      total: int, status: str = "running"):
        with contextlib.closing(self._connect()) as conn:
            conn.execute("""
                INSERT INTO scrape_progress (question_id, current_offset, 
                    total_expected, status, started_at)
                VALUES (?, ?, ?, ?, COALESCE(
                    (SELECT started_at FROM scrape_progress WHERE question_id=?), 
                    CURRENT_TIMESTAMP
                ))
                ON CONFLICT(question_id) DO UPDATE SET
                    current_offset=excluded.current_offset,
                    total_expected=excluded.total_expected,
                    status=excluded.status
            """, (question_id, offset, total, status, question_id))
            if status == "completed":
                conn.execute("""
                    UPDATE scrape_progress SET completed_at=CURRENT_TIMESTAMP
                    WHERE question_id=?
                """, (question_id,))
            conn.commit()

    def get_answers_for_export(self, question_id: str):
        """生成器，避免内存爆炸；同时附带图片 URL 列表"""
        with contextlib.closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM answers 
                WHERE question_id = ? 
                ORDER BY vote_count DESC
            """, (question_id,))
            for row in cursor:
                data = dict(row)
                img_rows = conn.execute(
                    "SELECT image_url FROM images WHERE answer_id = ?",
                    (data["answer_id"],)
                ).fetchall()
                data["images"] = [r[0] for r in img_rows]
                yield data