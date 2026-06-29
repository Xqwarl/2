import logging
from typing import Optional, List, Dict
from aiogram import Router, F
from aiogram.types import Message, Chat
from aiogram.filters import Command
from bot.db import (
    get_active_channel_pairs,
    get_channel_pair_by_tg_id,
    get_excluded_words,
    is_post_forwarded,
    add_forwarded_post,
    add_skipped_post
)
from bot.utils import extract_text_with_entities, check_excluded_words, convert_buttons
from bot.max_sender import MaxBotAPI

logger = logging.getLogger(__name__)

router = Router()

# Глобальная переменная для max_api
max_api: Optional[MaxBotAPI] = None


def set_max_api(api: MaxBotAPI):
    """Установить экземпляр Max API"""
    global max_api
    max_api = api


async def get_file_type(message: Message) -> Optional[str]:
    """Определить тип файла по сообщению"""
    if message.photo:
        return "image"
    elif message.video or message.video_note:
        return "video"
    elif message.audio:
        return "audio"
    elif message.document:
        return "file"
    return None


async def download_and_upload_media(message: Message, bot) -> Optional[str]:
    """
    Скачать медиа из TG и загрузить в Max
    Возвращает attachment token
    """
    try:
        file_type = await get_file_type(message)
        if not file_type:
            return None
        
        # Определяем file_id
        if message.photo:
            file_id = message.photo[-1].file_id
        elif message.video:
            file_id = message.video.file_id
        elif message.video_note:
            file_id = message.video_note.file_id
        elif message.audio:
            file_id = message.audio.file_id
        elif message.document:
            file_id = message.document.file_id
        else:
            return None
        
        # Скачиваем файл
        file = await bot.get_file(file_id)
        file_bytes = await bot.download_file(file.file_path)
        
        # Определяем имя файла
        if message.photo:
            filename = f"photo_{message.message_id}.jpg"
        elif message.video:
            filename = f"video_{message.message_id}.mp4"
        elif message.video_note:
            filename = f"video_note_{message.message_id}.mp4"
        elif message.audio:
            filename = f"audio_{message.message_id}.mp3"
        elif message.document:
            filename = message.document.file_name or f"file_{message.message_id}"
        else:
            filename = f"media_{message.message_id}"
        
        # Загружаем в Max
        token = await max_api.upload_from_memory(file_bytes, filename, file_type)
        return token
    
    except Exception as e:
        logger.error(f"Error downloading/uploading media: {e}")
        return None


async def process_media_group(messages: List[Message], bot, tg_channel_id: str, 
                             max_channel_id: str) -> List[Dict]:
    """
    Обработать медиа-группу (альбом)
    Возвращает список attachments для Max
    """
    attachments = []
    
    for msg in messages:
        token = await download_and_upload_media(msg, bot)
        if token:
            file_type = await get_file_type(msg)
            attachments.append({
                "type": file_type,
                "token": token
            })
    
    return attachments


@router.message(F.content_type.in_(["photo", "video", "audio", "document", "text"]))
async def handle_message(message: Message, bot):
    """Обработить сообщение из TG канала"""
    if not message.chat or message.chat.type != "supergroup":
        return
    
    tg_channel_id = str(message.chat.id)
    
    # Проверяем, активна ли пара каналов
    pair = await get_channel_pair_by_tg_id(tg_channel_id)
    if not pair or not pair.get("is_active"):
        return
    
    max_channel_id = pair.get("max_channel_id")
    tg_message_id = message.message_id
    
    # Проверяем дубли
    if await is_post_forwarded(tg_message_id, tg_channel_id):
        logger.info(f"Message {tg_message_id} already forwarded")
        return
    
    try:
        # Извлекаем текст
        text = extract_text_with_entities(message)
        
        # Проверяем слова-исключения
        excluded_words = await get_excluded_words(pair.get("id"))
        excluded = check_excluded_words(text, excluded_words)
        
        if excluded:
            logger.info(f"Message {tg_message_id} skipped due to excluded word: {excluded}")
            await add_skipped_post(tg_message_id, tg_channel_id, f"Excluded word: {excluded}")
            return
        
        # Собираем attachments
        attachments = []
        
        if message.photo:
            token = await download_and_upload_media(message, bot)
            if token:
                attachments.append({
                    "type": "image",
                    "token": token
                })
        elif message.video:
            token = await download_and_upload_media(message, bot)
            if token:
                attachments.append({
                    "type": "video",
                    "token": token
                })
        elif message.audio:
            token = await download_and_upload_media(message, bot)
            if token:
                attachments.append({
                    "type": "audio",
                    "token": token
                })
        elif message.document:
            token = await download_and_upload_media(message, bot)
            if token:
                attachments.append({
                    "type": "file",
                    "token": token
                })
        
        # Конвертируем кнопки
        buttons = None
        if message.reply_markup:
            buttons = convert_buttons(message.reply_markup)
        
        # Отправляем в Max
        success = await max_api.send_message(
            max_channel_id,
            text=text if text else None,
            attachments=attachments if attachments else None,
            buttons=buttons
        )
        
        if success:
            await add_forwarded_post(tg_message_id, tg_channel_id)
            logger.info(f"Message {tg_message_id} from {tg_channel_id} forwarded to {max_channel_id}")
        else:
            logger.error(f"Failed to forward message {tg_message_id}")
            await add_skipped_post(tg_message_id, tg_channel_id, "Failed to send to Max")
    
    except Exception as e:
        logger.error(f"Error processing message {tg_message_id}: {e}")
        await add_skipped_post(tg_message_id, tg_channel_id, f"Error: {str(e)}")
