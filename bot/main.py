import asyncio
import logging
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

from bot.db import init_db
from bot.tg_handler import router as tg_router, set_max_api
from bot.admin_panel import router as admin_router, set_admin_ids
from bot.max_sender import MaxBotAPI

# ============ Logging ============

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ============ Load Environment ============

load_dotenv()

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
MAX_BOT_TOKEN = os.getenv("MAX_BOT_TOKEN")
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")

if not TG_BOT_TOKEN or not MAX_BOT_TOKEN:
    logger.error("Missing TG_BOT_TOKEN or MAX_BOT_TOKEN in .env")
    exit(1)

# Parse admin IDs
try:
    ADMIN_IDS = [int(id.strip()) for id in ADMIN_IDS_STR.split(",") if id.strip()]
except ValueError:
    logger.error("Invalid ADMIN_IDS format in .env")
    ADMIN_IDS = []

logger.info(f"Admin IDs: {ADMIN_IDS}")

# ============ Bot Setup ============

async def main():
    """Точка входа"""
    
    # Инициализируем БД
    await init_db()
    logger.info("Database initialized")
    
    # Создаём Max API
    max_api = MaxBotAPI(MAX_BOT_TOKEN)
    await max_api.ensure_session()
    set_max_api(max_api)
    logger.info("Max API initialized")
    
    # Установим admin IDs в админ панель
    set_admin_ids(ADMIN_IDS)
    
    # Создаём бота
    bot = Bot(token=TG_BOT_TOKEN)
    dp = Dispatcher()
    
    # Регистрируем роутеры
    dp.include_router(tg_router)
    dp.include_router(admin_router)
    
    # Устанавливаем команды
    commands = [
        BotCommand(command="admin", description="Админ-панель"),
        BotCommand(command="start", description="Запуск бота"),
    ]
    await bot.set_my_commands(commands)
    
    # Запускаем polling
    logger.info("Starting bot...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except KeyboardInterrupt:
        logger.info("Bot stopped")
    finally:
        await max_api.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
