import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

import config
from database import init_db
from handlers import admin_handlers, user_handlers

# Log ayarları
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

async def main():
    logger.info("Veritabanı başlatılıyor...")
    await init_db()

    logger.info("Bot başlatılıyor...")
    # DefaultBotProperties kullanarak varsayılan özellikleri ayarlıyoruz
    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # Router'ları ekliyoruz (Önce admin router, sonra user)
    dp.include_router(admin_handlers.router)
    dp.include_router(user_handlers.router)

    # Eski güncellemeleri atlayıp yeni gelenleri dinlemeye başla
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot durduruldu.")
