import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
import config
from database import get_message_info, get_stats, ban_user, unban_user

router = Router()
logger = logging.getLogger(__name__)

# Sadece adminlerin komutları kullanabilmesi için basit bir filtre
def is_admin(message: Message) -> bool:
    return message.from_user.id in config.ADMIN_IDS

@router.message(Command("kim"), F.func(is_admin))
async def cmd_kim(message: Message):
    """
    Bir mesaja yanıt verip (reply) /kim yazarak veya '/kim <id>' yazarak mesajın sahibini bulur.
    """
    target_msg_id = None
    
    # Eğer bir mesaja yanıt verilmişse
    if message.reply_to_message:
        target_msg_id = message.reply_to_message.message_id
    else:
        # /kim 1234 formundaysa
        args = message.text.split()
        if len(args) > 1 and args[1].isdigit():
            target_msg_id = int(args[1])
            
    if not target_msg_id:
        await message.answer("Lütfen bir mesaja yanıt vererek `/kim` yazın veya `/kim <mesaj_id>` şeklinde kullanın.")
        return

    # Veritabanında ara (Admin kendi chatindeki bir mesaja bakıyor)
    author_info = await get_message_info(message.from_user.id, target_msg_id)
    if author_info:
        username_text = f"@{author_info['username']}" if author_info['username'] else "Yok"
        full_name = author_info['full_name'] or "Yok"
        user_id = author_info['original_user_id']
        tarih = author_info['timestamp'].strftime("%Y-%m-%d %H:%M:%S UTC")
        
        text = (
            f"🔍 <b>Mesaj Sahibi Bilgileri</b>\n\n"
            f"👤 İsim: {full_name}\n"
            f"🔗 Username: {username_text}\n"
            f"🆔 User ID: <code>{user_id}</code>\n"
            f"🕒 Zaman: {tarih}"
        )
        await message.answer(text)
    else:
        await message.answer("Bu mesaja ait log bulunamadı. (Sistemden önce atılmış veya silinmiş olabilir)")


@router.message(Command("stats"), F.func(is_admin))
async def cmd_stats(message: Message):
    """Sistem istatistiklerini gösterir."""
    stats = await get_stats()
    text = (
        f"📊 <b>Sistem İstatistikleri</b>\n\n"
        f"👥 Toplam Kullanıcı: {stats['total_users']}\n"
        f"🟢 Aktif Kullanıcı: {stats['active_users']}\n"
        f"💬 Loglanan Mesaj: {stats['total_messages']}\n"
        f"🚫 Banlı Kullanıcı: {stats['total_banned']}"
    )
    await message.answer(text)


@router.message(Command("ban"), F.func(is_admin))
async def cmd_ban(message: Message):
    """Kullanıcıyı sistemden uzaklaştırır. Kullanım: /ban <user_id>"""
    args = message.text.split()
    if len(args) > 1 and args[1].isdigit():
        user_id = int(args[1])
        await ban_user(user_id, reason="Admin tarafından yasaklandı")
        await message.answer(f"✅ <code>{user_id}</code> ID'li kullanıcı yasaklandı.")
    else:
        await message.answer("Kullanım: <code>/ban &lt;user_id&gt;</code>")

@router.message(Command("unban"), F.func(is_admin))
async def cmd_unban(message: Message):
    """Kullanıcının yasağını kaldırır. Kullanım: /unban <user_id>"""
    args = message.text.split()
    if len(args) > 1 and args[1].isdigit():
        user_id = int(args[1])
        await unban_user(user_id)
        await message.answer(f"✅ <code>{user_id}</code> ID'li kullanıcının yasağı kaldırıldı.")
    else:
        await message.answer("Kullanım: <code>/unban &lt;user_id&gt;</code>")
