import asyncio
import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import CommandStart
from aiogram.exceptions import TelegramForbiddenError
from database import (
    add_or_update_user, get_active_users, log_message, 
    set_user_inactive, get_message_info, get_target_message_id
)
import config

router = Router()
logger = logging.getLogger(__name__)

@router.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    success = await add_or_update_user(user.id, user.username, user.full_name)
    
    if not success:
        await message.answer("Sisteme erişiminiz kısıtlanmıştır.")
        return

    await message.answer(
        "👋 <b>Anonim Sohbet Botuna Hoşgeldin!</b>\n\n"
        "Buraya yazdığın (veya gönderdiğin fotoğraf/video gibi) her şey "
        "diğer tüm üyelere <b>tamamen anonim</b> olarak iletilecektir.\n"
        "İyi sohbetler! 🤫"
    )

@router.message(F.text | F.photo | F.video | F.voice | F.document | F.sticker | F.animation | F.audio)
async def handle_user_message(message: Message):
    user = message.from_user
    
    is_allowed = await add_or_update_user(user.id, user.username, user.full_name)
    if not is_allowed:
        return

    active_users = await get_active_users()
    target_users = [uid for uid in active_users if uid != user.id]
    
    # Kendi attığı mesajı da DB'ye loglayalım (kendi ekranındaki ID'si ile)
    # Böylece kendisine gelen/giden her şeyin bir referansı olur
    await log_message(
        original_user_id=user.id,
        original_message_id=message.message_id,
        target_user_id=user.id,
        target_message_id=message.message_id,
        content_type=message.content_type
    )

    if not target_users:
        return

    # Kullanıcı bir mesaja yanıt (reply) verdiyse, 
    # bu mesajın kime ait olduğunu (orijinal mesajı) bul.
    replied_info = None
    if message.reply_to_message:
        replied_info = await get_message_info(user.id, message.reply_to_message.message_id)

    # Admin broadcast kontrolü
    is_admin = user.id in config.ADMIN_IDS
    raw_text = message.text or message.caption or ""
    
    is_admin_broadcast = False
    modified_html = None
    
    if is_admin and raw_text.startswith("~"):
        is_admin_broadcast = True
        html_text = message.html_text or ""
        modified_html = html_text.replace("~", "", 1).strip() + "\n\n<b>Admin</b>"

    # Her bir kullanıcıya mesajı ilet
    for target_id in target_users:
        try:
            # Eğer yanıt verilen bir mesaj varsa, o kullanıcının (target_id) sohbetinde 
            # o mesajın hangi ID'ye denk geldiğini bulmamız lazım.
            reply_to_id = None
            if replied_info:
                # Orijinal mesajın target_id kullanıcısındaki kopyasının ID'sini bul
                reply_to_id = await get_target_message_id(
                    original_user_id=replied_info["original_user_id"],
                    original_message_id=replied_info["original_message_id"],
                    target_user_id=target_id
                )
            
            # Mesajı kopyala (eğer reply_to_id varsa o mesaja yanıt olarak gider)
            if is_admin_broadcast:
                if message.content_type == 'text':
                    copied_msg = await message.bot.send_message(
                        chat_id=target_id,
                        text=modified_html,
                        reply_to_message_id=reply_to_id
                    )
                else:
                    copied_msg = await message.copy_to(
                        chat_id=target_id,
                        reply_to_message_id=reply_to_id,
                        caption=modified_html
                    )
            else:
                copied_msg = await message.copy_to(
                    chat_id=target_id,
                    reply_to_message_id=reply_to_id
                )
            
            # Kopyalanan yeni mesajı veritabanına logla
            await log_message(
                original_user_id=user.id,
                original_message_id=message.message_id,
                target_user_id=target_id,
                target_message_id=copied_msg.message_id,
                content_type=message.content_type
            )
            
        except TelegramForbiddenError:
            await set_user_inactive(target_id)
        except Exception as e:
            logger.error(f"{target_id} ID'li kullanıcıya mesaj iletilemedi: {e}")
