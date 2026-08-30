import asyncio
import collections
import logging
from aiogram.exceptions import TelegramForbiddenError
from database import log_message, get_target_message_id, set_user_inactive

logger = logging.getLogger(__name__)

# Her kullanici icin ozel bir kilit olusturur
user_locks = collections.defaultdict(asyncio.Lock)

# Global rate limit: Telegram sunucularina anlik asiri yuklenmeyi (Spam ban) onlemek icin
global_semaphore = asyncio.Semaphore(25)

async def send_to_user_safely(
    bot,
    target_id: int,
    user_id: int,
    original_message,
    replied_info,
    modified_html
):
    """
    Belirli bir kullaniciya mesaj gonderme islemini siraya koyar.
    Bu kullaniciya ait onceki bir mesaj gonderimi devam ediyorsa, o bitene kadar bekler (user_locks).
    A ve B mesajlari atildiginda, eger kullanici A'yi henuz almadiysa, B mesaji A'nin bitmesini bekler.
    """
    async with user_locks[target_id]:
        # Telegram API hiz limitine takilmamak icin global semafor kullaniriz
        async with global_semaphore:
            try:
                reply_to_id = None
                if replied_info:
                    # Orijinal mesajin target_id kullanicisindaki kopyasinin ID'sini bul
                    reply_to_id = await get_target_message_id(
                        original_user_id=replied_info["original_user_id"],
                        original_message_id=replied_info["original_message_id"],
                        target_user_id=target_id
                    )
                
                # Mesaji kopyala veya metin olarak gonder
                if original_message.content_type == 'text':
                    copied_msg = await bot.send_message(
                        chat_id=target_id,
                        text=modified_html,
                        reply_to_message_id=reply_to_id
                    )
                else:
                    copied_msg = await original_message.copy_to(
                        chat_id=target_id,
                        reply_to_message_id=reply_to_id,
                        caption=modified_html
                    )
                
                # Veritabanina kaydet
                await log_message(
                    original_user_id=user_id,
                    original_message_id=original_message.message_id,
                    target_user_id=target_id,
                    target_message_id=copied_msg.message_id,
                    content_type=original_message.content_type
                )
                
            except TelegramForbiddenError:
                # Kullanici botu engellemis
                await set_user_inactive(target_id)
            except Exception as e:
                logger.error(f"{target_id} ID'li kullaniciya mesaj iletilemedi: {e}")
            finally:
                # Diger mesajlarin rahatca araya girebilmesi (interleaving) icin cok kucuk bir bekleme
                await asyncio.sleep(0.04)
