import asyncio
import logging
import html
import re
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import CommandStart
from aiogram.exceptions import TelegramForbiddenError
from database import (
    add_or_update_user, get_active_users, log_message, 
    set_user_inactive, get_message_info, get_target_message_id,
    is_moderator
)
from broadcast_manager import send_to_user_safely
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

    # Komutların (/start, /stats vb.) başkalarına gitmesini engelle
    raw_text_for_check = message.text or message.caption or ""
    if raw_text_for_check.startswith("/"):
        return

    # Admin ve Mod kontrolü
    is_admin = user.id in config.ADMIN_IDS
    is_mod = await is_moderator(user.id)

    # Referans linki kontrolü (Adminler ve Modlar hariç)
    if not is_admin and not is_mod:
        ref_pattern = r"(t\.me|telegram\.me)/[^\s]+[\?&](start|startapp|startbot|ref|referans|başlat|baslat)($|=|&)"
        if re.search(ref_pattern, raw_text_for_check, re.IGNORECASE):
            try:
                await message.delete()
            except Exception:
                pass
            await message.answer("❗ Referans linki paylaşmak yasaktır, mesajınız iletilmemiştir.")
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

    raw_text = message.text or message.caption or ""
    
    is_admin_broadcast = False
    modified_html = None
    
    if (is_admin or is_mod) and raw_text.startswith("~"):
        is_admin_broadcast = True
        html_text = message.html_text or ""
        tag = "Admin" if is_admin else "Moderatör"
        modified_html = html_text.replace("~", "", 1).strip() + f"\n\n<b>{tag}</b>"
    else:
        # Admin değilse veya ~ kullanmamışsa, tüm formatları (kalın, italik vb.) temizle
        if raw_text:
            modified_html = html.escape(raw_text)
        else:
            modified_html = None

    # Her bir kullanıcıya mesajı arka planda (asenkron kilitlerle) ilet
    for target_id in target_users:
        asyncio.create_task(
            send_to_user_safely(
                bot=message.bot,
                target_id=target_id,
                user_id=user.id,
                original_message=message,
                replied_info=replied_info,
                modified_html=modified_html
            )
        )
