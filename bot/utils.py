import re
import logging
from typing import List, Dict, Optional
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, 
    MessageEntity, Message
)

logger = logging.getLogger(__name__)

# Маппинг custom emoji на unicode
EMOJI_MAP = {
    "😀": "😀", "😁": "😁", "😂": "😂", "🤣": "🤣", "😃": "😃",
    "😄": "😄", "😅": "😅", "😆": "😆", "😉": "😉", "😊": "😊",
    "❤": "❤️", "🧡": "🧡", "💛": "💛", "💚": "💚", "💙": "💙",
}


def extract_text_with_entities(message: Message) -> str:
    """
    Извлечь текст из сообщения с учётом entities
    Заменяет MessageEntityCustomEmoji на unicode эмодзи
    """
    if message.text:
        text = message.text
    elif message.caption:
        text = message.caption
    else:
        return ""

    entities = message.entities or message.caption_entities or []
    
    # Обрабатываем entities в обратном порядке чтобы не сбилась нумерация
    for entity in sorted(entities, key=lambda e: e.offset, reverse=True):
        if entity.type == "custom_emoji" and entity.custom_emoji_id:
            # Пытаемся найти эмодзи по ID или используем стандартный
            emoji = EMOJI_MAP.get(entity.custom_emoji_id, "📌")
            text = text[:entity.offset] + emoji + text[entity.offset + entity.length:]
    
    return text


def convert_buttons(keyboard: Optional[InlineKeyboardMarkup]) -> Optional[Dict]:
    """Конвертить InlineKeyboardMarkup в buttons для Max"""
    if not keyboard:
        return None

    buttons = []
    for row in keyboard.inline_keyboard:
        max_row = []
        for btn in row:
            max_btn = {"text": btn.text}
            
            if btn.url:
                max_btn["type"] = "url"
                max_btn["url"] = btn.url
            elif btn.callback_data:
                max_btn["type"] = "callback"
                max_btn["callback_data"] = btn.callback_data
            elif btn.web_app:
                max_btn["type"] = "web_app"
                max_btn["url"] = btn.web_app.url
            else:
                continue
            
            max_row.append(max_btn)
        
        if max_row:
            buttons.append(max_row)
    
    return buttons if buttons else None


def check_excluded_words(text: str, excluded_words: List[dict]) -> Optional[str]:
    """
    Проверить, содержит ли текст слова-исключения
    Возвращает первое найденное слово или None
    """
    if not text:
        return None
    
    text_lower = text.lower()
    for word_obj in excluded_words:
        word = word_obj.get("word", "").lower()
        if word and word in text_lower:
            return word
    
    return None


def paginate_items(items: List, page: int, page_size: int = 5) -> tuple:
    """
    Пагинировать элементы
    Возвращает (текущая_страница, всего_страниц, элементы_на_странице)
    """
    total = len(items)
    total_pages = (total + page_size - 1) // page_size
    
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages
    
    start = (page - 1) * page_size
    end = start + page_size
    
    return page, total_pages, items[start:end]


def format_channel_pair_display(pair: dict) -> str:
    """Форматировать пару каналов для вывода"""
    tg_name = pair.get("tg_channel_username") or f"ID: {pair.get('tg_channel_id')}"
    max_id = pair.get("max_channel_id")
    status = "✅" if pair.get("is_active") else "❌"
    return f"{status} TG: @{tg_name} → MAX: {max_id}"


def format_statistics(pair_id: Optional[int] = None, all_pairs: List[dict] = None, 
                     forwarded_total: int = 0, skipped_total: int = 0,
                     last_forwarded: str = None) -> str:
    """Форматировать статистику"""
    stats = "📊 <b>Статистика</b>\n\n"
    
    if pair_id is None:
        # Общая статистика
        stats += f"✅ Всего переслано: {forwarded_total}\n"
        stats += f"⏭️ Всего пропущено: {skipped_total}\n"
    else:
        # Статистика по паре
        pair = next((p for p in all_pairs if p.get("id") == pair_id), None)
        if pair:
            tg_name = pair.get("tg_channel_username") or pair.get("tg_channel_id")
            stats += f"📡 Канал: @{tg_name}\n"
            stats += f"✅ Переслано: {forwarded_total}\n"
            stats += f"⏭️ Пропущено: {skipped_total}\n"
            if last_forwarded:
                stats += f"📅 Последняя пересылка: {last_forwarded[:19]}\n"
    
    return stats
