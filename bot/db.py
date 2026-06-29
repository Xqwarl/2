import aiosqlite
import logging
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "bot.db"


async def init_db():
    """Инициализация базы данных"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS channel_pairs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_channel_id TEXT NOT NULL,
                tg_channel_username TEXT,
                max_channel_id TEXT NOT NULL,
                is_active INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS excluded_words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT NOT NULL,
                channel_pair_id INTEGER DEFAULT NULL
            );

            CREATE TABLE IF NOT EXISTS forwarded_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_message_id INTEGER NOT NULL,
                tg_channel_id TEXT NOT NULL,
                forwarded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS skipped_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_message_id INTEGER NOT NULL,
                tg_channel_id TEXT NOT NULL,
                reason TEXT,
                skipped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        await db.commit()
    logger.info("Database initialized")


# ============ Channel Pairs ============

async def add_channel_pair(tg_channel_id: str, tg_channel_username: Optional[str], max_channel_id: str) -> int:
    """Добавить пару каналов"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO channel_pairs (tg_channel_id, tg_channel_username, max_channel_id) VALUES (?, ?, ?)",
            (tg_channel_id, tg_channel_username, max_channel_id)
        )
        await db.commit()
        logger.info(f"Added channel pair: TG {tg_channel_id} -> MAX {max_channel_id}")
        return cursor.lastrowid


async def get_all_channel_pairs() -> List[dict]:
    """Получить все пары каналов"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM channel_pairs")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_active_channel_pairs() -> List[dict]:
    """Получить активные пары каналов"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM channel_pairs WHERE is_active = 1")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_channel_pair_by_tg_id(tg_channel_id: str) -> Optional[dict]:
    """Получить пару по TG ID"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM channel_pairs WHERE tg_channel_id = ?",
            (tg_channel_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def toggle_channel_pair(pair_id: int, is_active: int):
    """Включить/выключить пару"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE channel_pairs SET is_active = ? WHERE id = ?",
            (is_active, pair_id)
        )
        await db.commit()
        logger.info(f"Toggled channel pair {pair_id} to {is_active}")


async def delete_channel_pair(pair_id: int):
    """Удалить пару и связанные слова-исключения"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM excluded_words WHERE channel_pair_id = ?", (pair_id,))
        await db.execute("DELETE FROM channel_pairs WHERE id = ?", (pair_id,))
        await db.commit()
        logger.info(f"Deleted channel pair {pair_id}")


# ============ Excluded Words ============

async def add_excluded_word(word: str, channel_pair_id: Optional[int] = None):
    """Добавить слово-исключение"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO excluded_words (word, channel_pair_id) VALUES (?, ?)",
            (word.lower(), channel_pair_id)
        )
        await db.commit()


async def add_excluded_words(words: List[str], channel_pair_id: Optional[int] = None):
    """Добавить несколько слов-исключений"""
    async with aiosqlite.connect(DB_PATH) as db:
        for word in words:
            await db.execute(
                "INSERT INTO excluded_words (word, channel_pair_id) VALUES (?, ?)",
                (word.lower().strip(), channel_pair_id)
            )
        await db.commit()
        logger.info(f"Added {len(words)} excluded words")


async def get_excluded_words(channel_pair_id: Optional[int] = None) -> List[dict]:
    """Получить слова-исключения (глобальные или по каналу)"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if channel_pair_id is None:
            cursor = await db.execute("SELECT * FROM excluded_words WHERE channel_pair_id IS NULL")
        else:
            cursor = await db.execute(
                "SELECT * FROM excluded_words WHERE channel_pair_id = ? OR channel_pair_id IS NULL",
                (channel_pair_id,)
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def delete_excluded_word(word_id: int):
    """Удалить слово-исключение"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM excluded_words WHERE id = ?", (word_id,))
        await db.commit()
        logger.info(f"Deleted excluded word {word_id}")


# ============ Forwarded Posts ============

async def add_forwarded_post(tg_message_id: int, tg_channel_id: str):
    """Добавить пост в таблицу переслано"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO forwarded_posts (tg_message_id, tg_channel_id) VALUES (?, ?)",
            (tg_message_id, tg_channel_id)
        )
        await db.commit()


async def is_post_forwarded(tg_message_id: int, tg_channel_id: str) -> bool:
    """Проверить, был ли пост уже переслан"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id FROM forwarded_posts WHERE tg_message_id = ? AND tg_channel_id = ?",
            (tg_message_id, tg_channel_id)
        )
        row = await cursor.fetchone()
        return row is not None


async def get_forwarded_count(tg_channel_id: Optional[str] = None) -> int:
    """Получить количество переслано"""
    async with aiosqlite.connect(DB_PATH) as db:
        if tg_channel_id is None:
            cursor = await db.execute("SELECT COUNT(*) FROM forwarded_posts")
        else:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM forwarded_posts WHERE tg_channel_id = ?",
                (tg_channel_id,)
            )
        result = await cursor.fetchone()
        return result[0] if result else 0


async def get_last_forwarded_date(tg_channel_id: str) -> Optional[str]:
    """Получить дату последней пересылки"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT forwarded_at FROM forwarded_posts WHERE tg_channel_id = ? ORDER BY forwarded_at DESC LIMIT 1",
            (tg_channel_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None


# ============ Skipped Posts ============

async def add_skipped_post(tg_message_id: int, tg_channel_id: str, reason: str):
    """Добавить пост в таблицу пропущено"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO skipped_posts (tg_message_id, tg_channel_id, reason) VALUES (?, ?, ?)",
            (tg_message_id, tg_channel_id, reason)
        )
        await db.commit()


async def get_skipped_count(tg_channel_id: Optional[str] = None) -> int:
    """Получить количество пропущено"""
    async with aiosqlite.connect(DB_PATH) as db:
        if tg_channel_id is None:
            cursor = await db.execute("SELECT COUNT(*) FROM skipped_posts")
        else:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM skipped_posts WHERE tg_channel_id = ?",
                (tg_channel_id,)
            )
        result = await cursor.fetchone()
        return result[0] if result else 0
