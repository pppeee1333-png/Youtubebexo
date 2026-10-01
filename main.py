import asyncio
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes,
    MessageHandler, filters
)
import yt_dlp

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "48"))
DOWNLOAD_TIMEOUT = int(os.getenv("DOWNLOAD_TIMEOUT", "900"))

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("youtube-music-bot")

YOUTUBE_RE = re.compile(
    r"^(https?://)?(www\.)?(youtube\.com/(watch\?v=|shorts/|live/)|youtu\.be/)",
    re.IGNORECASE
)

QUALITY_OPTIONS = {
    "64": "64 kbps",
    "128": "128 kbps",
    "192": "192 kbps",
    "320": "320 kbps",
}

def is_youtube_url(text: str) -> bool:
    return bool(YOUTUBE_RE.match(text.strip()))

def safe_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:180] or "audio"

def quality_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎧 64 kbps", callback_data="q:64"),
            InlineKeyboardButton("🎧 128 kbps", callback_data="q:128"),
        ],
        [
            InlineKeyboardButton("🎧 192 kbps", callback_data="q:192"),
            InlineKeyboardButton("🔥 320 kbps", callback_data="q:320"),
        ],
        [InlineKeyboardButton("❌ إلغاء", callback_data="cancel")]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("pending_url", None)
    await update.message.reply_text(
        "🎵 *YouTube Music Downloader*\n\n"
        "أرسل رابط أغنية أو فيديو من YouTube وسأحوّله إلى ملف صوتي.\n\n"
        "• يدعم روابط YouTube فقط\n"
        "• اختر جودة الصوت بعد إرسال الرابط\n"
        "• يتم حذف الملفات المؤقتة تلقائياً\n\n"
        "أرسل الرابط الآن 👇",
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *طريقة الاستخدام*\n\n"
        "1️⃣ أرسل رابط YouTube.\n"
        "2️⃣ اختر جودة الصوت.\n"
        "3️⃣ انتظر انتهاء التحويل.\n"
        "4️⃣ سيصلك الملف الصوتي.\n\n"
        "إذا حدث خطأ، حاول مرة أخرى أو أرسل رابطاً آخر.",
        parse_mode="Markdown"
    )

async def receive_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    url = update.message.text.strip()

    if not is_youtube_url(url):
        await update.message.reply_text(
            "❌ الرابط غير مدعوم.\n\n"
            "أرسل رابطاً من YouTube فقط، مثل:\n"
            "https://www.youtube.com/watch?v=..."
        )
        return

    context.user_data["pending_url"] = url
    await update.message.reply_text(
        "🎚️ اختر جودة الصوت:",
        reply_markup=quality_keyboard()
    )

async def quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        context.user_data.pop("pending_url", None)
        await query.edit_message_text("❌ تم إلغاء العملية.")
        return

    if not query.data.startswith("q:"):
        return

    quality = query.data.split(":", 1)[1]
    url = context.user_data.get("pending_url")

    if not url:
        await query.edit_message_text(
            "⚠️ انتهت صلاحية الطلب.\nأرسل رابط YouTube جديداً."
        )
        return

    await query.edit_message_text(
        f"⏳ جارٍ التحضير للجودة {QUALITY_OPTIONS.get(quality, quality + ' kbps')}...\n"
        "قد تستغرق العملية بعض الوقت."
    )

    chat_id = query.message.chat_id
    workdir = Path(tempfile.mkdtemp(prefix="ytmusic_"))

    try:
        await context.bot.send_chat_action(chat_id=chat_id, action="record_voice")

        info = await asyncio.to_thread(get_info, url)

        if not info:
            raise RuntimeError("لم يتم العثور على معلومات الفيديو.")

        title = safe_filename(info.get("title", "YouTube Audio"))
        duration = info.get("duration") or 0

        # حماية من الملفات الضخمة جداً قبل بدء التنزيل.
        if duration and duration > 60 * 60:
            raise ValueError("الفيديو أطول من ساعة، ولا يمكن معالجته عبر هذا البوت.")

        await context.bot.send_message(
            chat_id,
            f"🎵 *{title}*\n"
            f"⏱️ {format_duration(duration)}\n\n"
            "⬇️ جارٍ تنزيل الصوت وتحويله...",
            parse_mode="Markdown"
        )

        output_template = str(workdir / "%(title)s.%(ext)s")

        opts = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 30,
            "retries": 3,
            "fragment_retries": 3,
            "concurrent_fragment_downloads": 4,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": quality,
            }],
        }

        await asyncio.wait_for(
            asyncio.to_thread(download_audio, url, opts),
            timeout=DOWNLOAD_TIMEOUT
        )

        mp3_files = list(workdir.glob("*.mp3"))
        if not mp3_files:
            raise RuntimeError("فشل إنشاء ملف الصوت.")

        audio_file = mp3_files[0]
        size_mb = audio_file.stat().st_size / (1024 * 1024)

        if size_mb > MAX_FILE_MB:
            raise ValueError(
                f"حجم الملف {size_mb:.1f}MB ويتجاوز الحد المسموح {MAX_FILE_MB}MB."
            )

        await context.bot.send_chat_action(chat_id=chat_id, action="upload_voice")

        with audio_file.open("rb") as f:
            await context.bot.send_audio(
                chat_id=chat_id,
                audio=f,
                title=title,
                performer="YouTube",
                caption="🎵 تم التحميل بنجاح",
                read_timeout=120,
                write_timeout=120,
                connect_timeout=30,
            )

        context.user_data.pop("pending_url", None)

        await context.bot.send_message(
            chat_id,
            "✅ تم التحميل بنجاح!\n\nأرسل رابط YouTube آخر للتحميل."
        )

    except asyncio.TimeoutError:
        logger.warning("Download timeout for user %s", query.from_user.id)
        await context.bot.send_message(
            chat_id,
            "❌ حدث خطأ: انتهى وقت المعالجة.\nحاول مرة أخرى أو استخدم فيديو أقصر."
        )
    except yt_dlp.utils.DownloadError as e:
        logger.warning("yt-dlp error: %s", str(e)[:500])
        await context.bot.send_message(
            chat_id,
            "❌ تعذر تحميل هذا الرابط.\n"
            "تأكد أن الفيديو متاح للعامة على YouTube ثم حاول مرة أخرى."
        )
    except ValueError as e:
        await context.bot.send_message(chat_id, f"⚠️ {e}")
    except Exception:
        logger.exception("Unexpected error")
        await context.bot.send_message(
            chat_id,
            "❌ حدث خطأ غير متوقع أثناء التحميل.\n"
            "حاول مرة أخرى بعد قليل."
        )
    finally:
        context.user_data.pop("pending_url", None)
        shutil.rmtree(workdir, ignore_errors=True)

def get_info(url):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 20,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)

def download_audio(url, opts):
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

def format_duration(seconds):
    try:
        seconds = int(seconds)
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
    except Exception:
        return "غير معروف"

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled Telegram error", exc_info=context.error)
    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                "❌ حدث خطأ غير متوقع.\nحاول مرة أخرى."
            )
    except Exception:
        pass

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN غير موجود في متغيرات البيئة.")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(quality_callback, pattern=r"^(q:\d+|cancel)$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_url))
    app.add_error_handler(error_handler)

    logger.info("Bot is running...")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )

if __name__ == "__main__":
    main()
