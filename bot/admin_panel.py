import logging
from typing import Optional, List, Dict
from aiogram import Router, F, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message

from bot.db import (
    get_all_channel_pairs,
    get_active_channel_pairs,
    add_channel_pair,
    toggle_channel_pair,
    delete_channel_pair,
    get_excluded_words,
    add_excluded_words,
    delete_excluded_word,
    get_forwarded_count,
    get_skipped_count,
    get_last_forwarded_date
)
from bot.utils import paginate_items, format_channel_pair_display, format_statistics

logger = logging.getLogger(__name__)

router = Router()

# Admin IDs будут установлены при инициализации
ADMIN_IDS: List[int] = []


def set_admin_ids(ids: List[int]):
    """Установить IDs администраторов"""
    global ADMIN_IDS
    ADMIN_IDS = ids


def is_admin(user_id: int) -> bool:
    """Проверить, является ли пользователь администратором"""
    return user_id in ADMIN_IDS


# ============ FSM States ============

class AdminStates(StatesGroup):
    main_menu = State()
    channels_menu = State()
    add_channel_tg = State()
    add_channel_max = State()
    add_channel_confirm = State()
    channels_page = State()
    words_menu = State()
    words_type = State()
    words_select_channel = State()
    words_list = State()
    add_word = State()
    stats_menu = State()
    stats_detail = State()


# ============ Main Menu ============

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    """Открыть админ-панель"""
    if not is_admin(message.from_user.id):
        await message.reply("❌ У вас нет доступа")
        return
    
    await show_main_menu(message, state)


async def show_main_menu(message: Message, state: FSMContext):
    """Показать главное меню"""
    text = "🔧 <b>Админ-панель</b>\n\nВыберите раздел:"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📡 Каналы", callback_data="channels")],
        [InlineKeyboardButton(text="🚫 Слова-исключения", callback_data="words")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
    ])
    
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(AdminStates.main_menu)


# ============ Channels Section ============

@router.callback_query(F.data == "channels", StateFilter(AdminStates.main_menu))
async def channels_menu(query: types.CallbackQuery, state: FSMContext):
    """Открыть раздел каналов"""
    await show_channels_page(query, state, page=1)


async def show_channels_page(query: types.CallbackQuery, state: FSMContext, page: int = 1):
    """Показать страницу с каналами"""
    pairs = await get_all_channel_pairs()
    page, total_pages, page_items = paginate_items(pairs, page, page_size=5)
    
    text = f"📡 <b>Пары каналов</b> (страница {page}/{total_pages})\n\n"
    
    if not page_items:
        text += "Пар каналов не добавлено"
    else:
        for pair in page_items:
            display = format_channel_pair_display(pair)
            text += f"{display}\n"
    
    keyboard = []
    
    # Кнопки для каждой пары на этой странице
    for pair in page_items:
        pair_id = pair.get("id")
        tg_name = pair.get("tg_channel_username") or pair.get("tg_channel_id")
        toggle_state = "0" if pair.get("is_active") else "1"
        
        keyboard.append([
            InlineKeyboardButton(text="✅" if pair.get("is_active") else "❌", 
                               callback_data=f"toggle_channel:{pair_id}:{toggle_state}"),
            InlineKeyboardButton(text="🗑", callback_data=f"delete_channel:{pair_id}"),
        ])
    
    # Пагинация
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"channels_page:{page-1}"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="Вперед ▶️", callback_data=f"channels_page:{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Кнопки действий
    keyboard.append([InlineKeyboardButton(text="➕ Добавить пару", callback_data="add_channel")])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_main")])
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="HTML")
    await state.set_state(AdminStates.channels_page)


@router.callback_query(F.data.startswith("channels_page:"))
async def channels_page_nav(query: types.CallbackQuery, state: FSMContext):
    """Навигация по страницам каналов"""
    page = int(query.data.split(":")[1])
    await show_channels_page(query, state, page)


@router.callback_query(F.data == "add_channel")
async def add_channel_start(query: types.CallbackQuery, state: FSMContext):
    """Начать добавление пары"""
    text = "📡 <b>Добавить пару каналов</b>\n\n" \
           "Введите username или ID Telegram канала\n\n" \
           "Примеры:\n" \
           "• @mychannel\n" \
           "• -1001234567890"
    
    await query.message.edit_text(text, parse_mode="HTML")
    await state.set_state(AdminStates.add_channel_tg)


@router.message(StateFilter(AdminStates.add_channel_tg))
async def add_channel_tg(message: Message, state: FSMContext):
    """Ввести TG канал"""
    tg_channel = message.text.strip()
    
    if not tg_channel:
        await message.reply("❌ Пустой ввод")
        return
    
    await state.update_data(tg_channel=tg_channel)
    
    text = "🔗 <b>Введите ID канала в Max</b>\n\n" \
           "Пример: 12345"
    
    await message.answer(text, parse_mode="HTML")
    await state.set_state(AdminStates.add_channel_max)


@router.message(StateFilter(AdminStates.add_channel_max))
async def add_channel_max(message: Message, state: FSMContext):
    """Ввести Max канал"""
    max_channel = message.text.strip()
    
    if not max_channel:
        await message.reply("❌ Пустой ввод")
        return
    
    data = await state.get_data()
    tg_channel = data.get("tg_channel")
    
    # Определяем username и ID
    if tg_channel.startswith("@"):
        tg_username = tg_channel[1:]
        tg_id = tg_channel
    else:
        tg_username = None
        tg_id = tg_channel
    
    text = f"✅ <b>Подтверждение</b>\n\n" \
           f"Telegram: {tg_channel}\n" \
           f"Max: {max_channel}\n\n" \
           f"Всё верно?"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Добавить", callback_data="confirm_add_channel"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add_channel")],
    ])
    
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await state.update_data(tg_id=tg_id, tg_username=tg_username, max_channel=max_channel)
    await state.set_state(AdminStates.add_channel_confirm)


@router.callback_query(F.data == "confirm_add_channel")
async def confirm_add_channel(query: types.CallbackQuery, state: FSMContext):
    """Подтвердить добавление пары"""
    data = await state.get_data()
    tg_id = data.get("tg_id")
    tg_username = data.get("tg_username")
    max_channel = data.get("max_channel")
    
    try:
        await add_channel_pair(tg_id, tg_username, max_channel)
        await query.answer("✅ Пара добавлена")
        await show_channels_page(query, state, page=1)
    except Exception as e:
        logger.error(f"Error adding channel pair: {e}")
        await query.answer("❌ Ошибка при добавлении")


@router.callback_query(F.data == "cancel_add_channel")
async def cancel_add_channel(query: types.CallbackQuery, state: FSMContext):
    """Отменить добавление"""
    await show_channels_page(query, state, page=1)


@router.callback_query(F.data.startswith("toggle_channel:"))
async def toggle_channel(query: types.CallbackQuery, state: FSMContext):
    """Переключить статус канала"""
    parts = query.data.split(":")
    pair_id = int(parts[1])
    is_active = int(parts[2])
    
    try:
        await toggle_channel_pair(pair_id, is_active)
        await query.answer("✅ Статус изменён")
        await show_channels_page(query, state, page=1)
    except Exception as e:
        logger.error(f"Error toggling channel: {e}")
        await query.answer("❌ Ошибка")


@router.callback_query(F.data.startswith("delete_channel:"))
async def delete_channel(query: types.CallbackQuery, state: FSMContext):
    """Удалить пару"""
    pair_id = int(query.data.split(":")[1])
    
    try:
        await delete_channel_pair(pair_id)
        await query.answer("✅ Пара удалена")
        await show_channels_page(query, state, page=1)
    except Exception as e:
        logger.error(f"Error deleting channel: {e}")
        await query.answer("❌ Ошибка")


# ============ Excluded Words Section ============

@router.callback_query(F.data == "words", StateFilter(AdminStates.main_menu))
async def words_menu(query: types.CallbackQuery, state: FSMContext):
    """Открыть раздел слов-исключений"""
    text = "🚫 <b>Слова-исключения</b>\n\nВыберите тип:"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌍 Глобальные", callback_data="words_global")],
        [InlineKeyboardButton(text="📡 По каналу", callback_data="words_by_channel")],
        [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_main")],
    ])
    
    await query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(AdminStates.words_type)


@router.callback_query(F.data == "words_global")
async def words_global(query: types.CallbackQuery, state: FSMContext):
    """Показать глобальные слова-исключения"""
    words = await get_excluded_words(channel_pair_id=None)
    
    text = "🌍 <b>Глобальные слова-исключения</b>\n\n"
    
    keyboard = []
    if words:
        for word in words:
            text += f"• {word.get('word')}\n"
            keyboard.append([
                InlineKeyboardButton(text="🗑", callback_data=f"delete_word:{word.get('id')}")
            ])
    else:
        text += "Нет добавленных слов"
    
    keyboard.append([InlineKeyboardButton(text="➕ Добавить", callback_data="add_word_global")])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="words")])
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="HTML")
    await state.set_state(AdminStates.words_list)


@router.callback_query(F.data == "words_by_channel")
async def words_by_channel(query: types.CallbackQuery, state: FSMContext):
    """Выбрать канал для слов-исключений"""
    pairs = await get_all_channel_pairs()
    
    if not pairs:
        await query.answer("❌ Нет добавленных пар каналов")
        return
    
    text = "📡 <b>Выберите канал</b>:"
    
    keyboard = []
    for pair in pairs:
        tg_name = pair.get("tg_channel_username") or pair.get("tg_channel_id")
        keyboard.append([
            InlineKeyboardButton(text=f"@{tg_name}", callback_data=f"words_ch:{pair.get('id')}")
        ])
    
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="words")])
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="HTML")


@router.callback_query(F.data.startswith("words_ch:"))
async def words_channel(query: types.CallbackQuery, state: FSMContext):
    """Показать слова для конкретного канала"""
    pair_id = int(query.data.split(":")[1])
    
    pairs = await get_all_channel_pairs()
    pair = next((p for p in pairs if p.get("id") == pair_id), None)
    
    if not pair:
        await query.answer("❌ Канал не найден")
        return
    
    words = await get_excluded_words(channel_pair_id=pair_id)
    
    tg_name = pair.get("tg_channel_username") or pair.get("tg_channel_id")
    text = f"📡 <b>Слова для @{tg_name}</b>\n\n"
    
    keyboard = []
    if words:
        for word in words:
            if word.get("channel_pair_id") == pair_id:  # Показываем только локальные
                text += f"• {word.get('word')}\n"
                keyboard.append([
                    InlineKeyboardButton(text="🗑", callback_data=f"delete_word:{word.get('id')}")
                ])
    else:
        text += "Нет добавленных слов"
    
    keyboard.append([InlineKeyboardButton(text="➕ Добавить", callback_data=f"add_word_ch:{pair_id}")])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="words_by_channel")])
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="HTML")
    await state.set_state(AdminStates.words_list)


@router.callback_query(F.data == "add_word_global")
async def add_word_global(query: types.CallbackQuery, state: FSMContext):
    """Начать добавление глобального слова"""
    text = "🌍 <b>Добавить глобальное слово-исключение</b>\n\n" \
           "Введите слово или несколько слов через запятую:\n\n" \
           "Примеры:\n" \
           "• spam\n" \
           "• spam, abuse, spam2"
    
    await query.message.edit_text(text, parse_mode="HTML")
    await state.update_data(word_type="global", word_pair_id=None)
    await state.set_state(AdminStates.add_word)


@router.callback_query(F.data.startswith("add_word_ch:"))
async def add_word_channel(query: types.CallbackQuery, state: FSMContext):
    """Начать добавление слова для канала"""
    pair_id = int(query.data.split(":")[1])
    
    text = "📡 <b>Добавить слово-исключение для канала</b>\n\n" \
           "Введите слово или несколько слов через запятую"
    
    await query.message.edit_text(text, parse_mode="HTML")
    await state.update_data(word_type="channel", word_pair_id=pair_id)
    await state.set_state(AdminStates.add_word)


@router.message(StateFilter(AdminStates.add_word))
async def add_word(message: Message, state: FSMContext):
    """Обработать ввод слов"""
    data = await state.get_data()
    word_type = data.get("word_type")
    word_pair_id = data.get("word_pair_id")
    
    words_input = message.text.strip()
    words_list = [w.strip() for w in words_input.split(",") if w.strip()]
    
    if not words_list:
        await message.reply("❌ Пустой ввод")
        return
    
    try:
        await add_excluded_words(words_list, channel_pair_id=word_pair_id)
        await message.answer(f"✅ Добавлено {len(words_list)} слов(а)")
        
        # Вернуться в меню слов
        if word_type == "global":
            await state.clear()
            await message.answer("Выполнено")
        else:
            await state.clear()
            await message.answer("Выполнено")
    
    except Exception as e:
        logger.error(f"Error adding words: {e}")
        await message.reply("❌ Ошибка при добавлении")


@router.callback_query(F.data.startswith("delete_word:"))
async def delete_word(query: types.CallbackQuery, state: FSMContext):
    """Удалить слово-исключение"""
    word_id = int(query.data.split(":")[1])
    
    try:
        await delete_excluded_word(word_id)
        await query.answer("✅ Слово удалено")
        await state.clear()
        await query.message.answer("Выполнено. Используйте /admin для возврата в меню")
    except Exception as e:
        logger.error(f"Error deleting word: {e}")
        await query.answer("❌ Ошибка")


# ============ Statistics Section ============

@router.callback_query(F.data == "stats", StateFilter(AdminStates.main_menu))
async def stats_menu(query: types.CallbackQuery, state: FSMContext):
    """Открыть раздел статистики"""
    forwarded = await get_forwarded_count()
    skipped = await get_skipped_count()
    
    text = f"📊 <b>Статистика</b>\n\n" \
           f"✅ Всего переслано: {forwarded}\n" \
           f"⏭️ Всего пропущено: {skipped}\n\n" \
           f"Выберите действие:"
    
    pairs = await get_all_channel_pairs()
    keyboard = []
    
    for pair in pairs:
        tg_name = pair.get("tg_channel_username") or pair.get("tg_channel_id")
        keyboard.append([
            InlineKeyboardButton(text=f"📡 @{tg_name}", callback_data=f"stats_pair:{pair.get('id')}")
        ])
    
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_main")])
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="HTML")
    await state.set_state(AdminStates.stats_menu)


@router.callback_query(F.data.startswith("stats_pair:"))
async def stats_pair(query: types.CallbackQuery, state: FSMContext):
    """Показать статистику по конкретной паре"""
    pair_id = int(query.data.split(":")[1])
    
    pairs = await get_all_channel_pairs()
    pair = next((p for p in pairs if p.get("id") == pair_id), None)
    
    if not pair:
        await query.answer("❌ Канал не найден")
        return
    
    tg_channel_id = pair.get("tg_channel_id")
    forwarded = await get_forwarded_count(tg_channel_id)
    skipped = await get_skipped_count(tg_channel_id)
    last_date = await get_last_forwarded_date(tg_channel_id)
    
    tg_name = pair.get("tg_channel_username") or tg_channel_id
    text = f"📡 <b>Статистика: @{tg_name}</b>\n\n" \
           f"✅ Переслано: {forwarded}\n" \
           f"⏭️ Пропущено: {skipped}\n"
    
    if last_date:
        text += f"📅 Последняя пересылка: {last_date[:19]}\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="stats")],
    ])
    
    await query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "back_main")
async def back_main(query: types.CallbackQuery, state: FSMContext):
    """Вернуться в главное меню"""
    await show_main_menu(query.message, state)


@router.callback_query(F.data == "words")
async def back_words(query: types.CallbackQuery, state: FSMContext):
    """Вернуться в меню слов"""
    await words_menu(query, state)
