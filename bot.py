import os
import json
import time
import asyncio
import re
import requests

from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    FSInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from yt_dlp import YoutubeDL

# === КОНФИГ ===
TOKEN = "7772820876:AAEGz0yX4iPzL4fxkBBeOmwtk0KmRe966e0"
ADMIN_IDS = [8099763592, 5764884543, 5056559064]
INSTAGRAM_SESSIONID = "57322342565%3ADzHnlXozV05Q4U%3A1%3AAYc4VUdw1gsc9pGSIKsp03uVN0Sr2O3IopIevDKtVQ"

bot = Bot(token=TOKEN)
dp = Dispatcher()

USERS_FILE = "users.json"
STATS_FILE = "stats.json"
ERROR_LOG = "errors.log"
user_states = {}
UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"
)

bot_enabled = True

# === УТИЛИТЫ ===
def get_admin_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Получить статистику"),
                KeyboardButton(text="Рассылка"),
            ],
            [
                KeyboardButton(text="Выключить бота"),
                KeyboardButton(text="Включить бота"),
            ],
        ],
        resize_keyboard=True,
    )

def is_sleep_time() -> bool:
    now_utc = datetime.utcnow()
    msk = now_utc + timedelta(hours=3)
    return 1 <= msk.hour < 6

def log_error(e: Exception):
    with open(ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {e}\n")

def update_user(uid: int):
    try:
        users = json.load(open(USERS_FILE, encoding="utf-8"))
    except:
        users = {}
    users[str(uid)] = int(time.time())
    json.dump(users, open(USERS_FILE, "w", encoding="utf-8"), ensure_ascii=False)

def increment_downloads():
    try:
        stats = json.load(open(STATS_FILE, encoding="utf-8"))
    except:
        stats = {"downloads": 0}
    stats["downloads"] += 1
    json.dump(stats, open(STATS_FILE, "w", encoding="utf-8"), ensure_ascii=False)

def resolve_redirect(url: str) -> str:
    try:
        return requests.head(url, allow_redirects=True, timeout=8).url
    except:
        return url

def ig_cookiefile() -> str:
    path = "cookies_ig.txt"
    exp = int(time.time()) + 90 * 86400
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Netscape HTTP Cookie File\n")
        f.write(
            f".instagram.com\tTRUE\t/\tTRUE\t{exp}\tsessionid\t{INSTAGRAM_SESSIONID}\n"
        )
    return path

def plural_hours(h: int) -> str:
    if h == 1:
        return "1 час"
    if 2 <= h <= 4:
        return f"{h} часа"
    return f"{h} часов"

def plural_minutes(m: int) -> str:
    if m == 1:
        return "1 минуту"
    if 2 <= m <= 4:
        return f"{m} минуты"
    return f"{m} минут"

# === ЗАГРУЗЧИКИ ===
def dl_instagram(url: str) -> str:
    try:
        with YoutubeDL(
            {
                "quiet": True,
                "noplaylist": True,
                "format": "mp4[filesize<50M]/best",
                "merge_output_format": "mp4",
                "outtmpl": "insta.%(ext)s",
                "http_headers": {"User-Agent": UA},
                "cookiefile": ig_cookiefile(),
            }
        ) as y:
            info = y.extract_info(url, download=True)
            return y.prepare_filename(info)
    except Exception as e:
        log_error(f"yt_dlp IG fail: {e}")

    m = re.search(r"(?:/p/|/reel/|/tv/)([^/?#&]+)", url)
    if not m:
        raise Exception("Shortcode IG не найдено")

    shortcode = m.group(1)
    embed_url = f"https://www.instagram.com/p/{shortcode}/embed/"
    cookies = {"sessionid": INSTAGRAM_SESSIONID}
    r = requests.get(embed_url, headers={"User-Agent": UA}, cookies=cookies, timeout=15)

    m1 = (
        re.search(
            r'<meta[^>]+property="og:video"[^>]+content="([^"]+)"', r.text
        )
        or re.search(r'<video[^>]+src="([^"]+)"', r.text)
    )
    if not m1:
        raise Exception("Видео в embed IG не найдено")

    vurl = m1.group(1)
    fn = "insta_fb.mp4"
    with requests.get(
        vurl, headers={"User-Agent": UA}, cookies=cookies, stream=True, timeout=30
    ) as rs:
        rs.raise_for_status()
        with open(fn, "wb") as f:
            for chunk in rs.iter_content(8192):
                if chunk:
                    f.write(chunk)
    return fn

def dl_tiktok(url: str) -> str:
    with YoutubeDL(
        {
            "quiet": True,
            "noplaylist": True,
            "format": "mp4[filesize<50M]/best",
            "merge_output_format": "mp4",
            "outtmpl": "tiktok.%(ext)s",
            "http_headers": {"User-Agent": UA, "Referer": "https://www.tiktok.com/"},
        }
    ) as y:
        info = y.extract_info(url, download=True)
        return y.prepare_filename(info)

# === HANDLERS ===
@dp.message(CommandStart())
async def cmd_start(m: Message):
    global bot_enabled

    if not bot_enabled:
        await m.answer("🤖 Бот временно не работает.")
        return

    if is_sleep_time():
        await m.answer("😴 Бот отдыхает с 01:00 до 06:00 по МСК.\nПопробуйте позже.")
        return

    update_user(m.from_user.id)
    kb = get_admin_kb() if m.from_user.id in ADMIN_IDS else None

    await m.answer(
        "👋 Добро пожаловать!\n\n"
        "Скинь ссылку на TikTok или Instagram — и получи видео без ограничений по качеству.\n\n"
        "📢 Новости: @TokDropX",
        reply_markup=kb,
    )


@dp.message()
async def handle_message(m: Message):
    global bot_enabled
    uid = m.from_user.id
    text_raw = (m.text or "").strip()
    low = text_raw.lower()

    # — админ: выключить/включить бота —
    if uid in ADMIN_IDS and low == "выключить бота":
        if not bot_enabled:
            await m.answer("⚠️ Бот уже выключен.", reply_markup=get_admin_kb())
            return
        bot_enabled = False
        try:
            users = json.load(open(USERS_FILE, encoding="utf-8"))
        except:
            users = {}
        for u in users:
            try:
                await bot.send_message(int(u), "🤖 Бот временно не работает.")
                await asyncio.sleep(0.05)
            except:
                pass
        await m.answer("✅ Бот выключен.", reply_markup=get_admin_kb())
        return

    if uid in ADMIN_IDS and low == "включить бота":
        if bot_enabled:
            await m.answer("⚠️ Бот уже включен.", reply_markup=get_admin_kb())
            return
        bot_enabled = True
        try:
            users = json.load(open(USERS_FILE, encoding="utf-8"))
        except:
            users = {}
        for u in users:
            try:
                await bot.send_message(int(u), "✅ Бот снова работает.")
                await asyncio.sleep(0.05)
            except:
                pass
        await m.answer("✅ Бот включен.", reply_markup=get_admin_kb())
        return

    if not bot_enabled:
        return

    if is_sleep_time():
        await m.answer("😴 Время сна (01:00–06:00 МСК). Попробуйте позже.")
        return

    # — статистика —
    if uid in ADMIN_IDS and low == "получить статистику":
        try:
            users = (
                json.load(open(USERS_FILE, encoding="utf-8"))
                if os.path.exists(USERS_FILE)
                else {}
            )
            stats = (
                json.load(open(STATS_FILE, encoding="utf-8"))
                if os.path.exists(STATS_FILE)
                else {"downloads": 0}
            )
            active = sum(1 for t in users.values() if time.time() - t < 7 * 86400)
            await m.answer(
                f"📊 Всего пользователей: {len(users)}\n"
                f"Активных за 7 дней: {active}\n"
                f"Скачиваний: {stats.get('downloads', 0)}",
                reply_markup=get_admin_kb(),
            )
        except Exception as e:
            log_error(e)
            await m.answer("Ошибка статистики.", reply_markup=get_admin_kb())
        return

    # — запуск рассылки —
    if uid in ADMIN_IDS and low == "рассылка":
        user_states[uid] = {"step": "text"}
        await m.answer("✏️ Введите текст рассылки:")
        return

    # — этапы рассылки —
    if uid in ADMIN_IDS and uid in user_states:
        st = user_states[uid]

        if st["step"] == "text":
            st["text"] = text_raw
            st["step"] = "buttons"
            skip_kb = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="Пропустить")]],
                resize_keyboard=True,
            )
            await m.answer(
                "🔘 Введите кнопки (Каждая строка: Текст - URL) или 'Пропустить':",
                reply_markup=skip_kb,
            )
            return

        if st["step"] == "buttons":
            kb_markup = None
            if low != "пропустить":
                buttons = []
                for line in text_raw.splitlines():
                    if "-" in line:
                        t, u = line.split("-", 1)
                        t, u = t.strip(), u.strip()
                        if t and u:
                            buttons.append(
                                [InlineKeyboardButton(text=t, url=u)]
                            )
                if buttons:
                    kb_markup = InlineKeyboardMarkup(inline_keyboard=buttons)

            st["buttons"] = kb_markup
            st["step"] = "time"
            skip_kb = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="Пропустить")]],
                resize_keyboard=True,
            )
            await m.answer(
                "🕒 Введите время (ДД.MM.YYYY чч:мм) или 'Пропустить':",
                reply_markup=skip_kb,
            )
            return

        if st["step"] == "time":
            if low == "пропустить":
                send_at = time.time()
            else:
                try:
                    send_at = datetime.strptime(text_raw, "%d.%m.%Y %H:%M").timestamp()
                except:
                    await m.answer("❌ Формат неверен, попробуйте ДД.MM.YYYY чч:мм")
                    return

            # сразу возвращаем полное админ-меню
            await m.answer("✅ Рассылка запланирована.", reply_markup=get_admin_kb())

            await asyncio.sleep(max(0, send_at - time.time()))

            # отправляем рассылку
            start_send = time.time()
            try:
                users = (
                    json.load(open(USERS_FILE, encoding="utf-8"))
                    if os.path.exists(USERS_FILE)
                    else {}
                )
            except:
                users = {}

            sent, total = 0, len(users)
            preview = await bot.send_message(uid, st["text"], reply_markup=st.get("buttons"))

            for u in users:
                try:
                    await bot.send_message(int(u), st["text"], reply_markup=st.get("buttons"))
                    sent += 1
                    await asyncio.sleep(0.05)
                except Exception as e:
                    log_error(e)

            end_send = time.time()
            duration = int(end_send - start_send)
            hrs = duration // 3600
            mins = (duration % 3600) // 60
            duration_text = f"{plural_hours(hrs)} {plural_minutes(mins)}"

            await bot.send_message(
                uid,
                (
                    f"📤 Рассылка завершена\n"
                    f"✅ Отправлено: {sent} из {total}\n"
                    f"длилась {duration_text}"
                ),
                reply_to_message_id=preview.message_id,
                reply_markup=get_admin_kb(),
            )
            user_states.pop(uid, None)
            return

    # === Загрузка видео ===
    if any(d in low for d in ("instagram.com","instagr.am","tiktok.com","vm.tiktok.com")):
        if "vm.tiktok.com" in low:
            text_raw = resolve_redirect(text_raw)
            low = text_raw.lower()

        loading = await m.answer("⏳ Скачиваю видео…")
        try:
            fn = (
                dl_instagram(text_raw)
                if "instagram.com" in low or "instagr.am" in low
                else dl_tiktok(text_raw)
            )

            if os.path.getsize(fn) > 50 * 1024 * 1024:
                await m.answer("❌ Файл слишком большой для Telegram.")
            else:
                await m.answer_video(
                    FSInputFile(fn),
                    caption="Вот ваше видео 🎬\nСпасибо, что пользуетесь нашим ботом — @TokDropXBot",
                )
                increment_downloads()

            os.remove(fn)
        except Exception as e:
            log_error(e)
            await m.answer("⚠️ Не удалось скачать видео.")
        finally:
            try:
                await bot.delete_message(chat_id=m.chat.id, message_id=loading.message_id)
            except:
                pass
        return

    # иначе молчим

# === ЗАПУСК ===
if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))
