import os
import logging
import tempfile
import signal
import sys
from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from telegram.error import Conflict, TimedOut, NetworkError
from PIL import Image
import pytesseract
from fpdf import FPDF
from transliterate import translit
import asyncio

# Налаштування логування
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Ensure tesseract is in PATH if needed (for Docker)
pytesseract.pytesseract.tesseract_cmd = "tesseract"

# Глобальна змінна для application
application = None

def safe_text_for_pdf(text):
    """Безпечно обробляє текст для PDF"""
    try:
        # Спроба зберегти оригінальний текст
        test_text = text.encode('latin1')
        return text
    except UnicodeEncodeError:
        # Якщо не вдається, транслітеруємо українські символи
        try:
            return translit(text, 'uk', reversed=True)
        except:
            # Останній варіант - видаляємо неприпустимі символи
            return text.encode('ascii', 'ignore').decode('ascii')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник команди /start"""
    await update.message.reply_text("👋 Надішли мені зображення або скан, і я згенерую PDF з текстом!")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник фотографій"""
    try:
        # Повідомлення про початок обробки
        processing_msg = await update.message.reply_text("📷 Обробляю зображення...")
        
        file = await update.message.photo[-1].get_file()
        
        # Використовуємо тимчасові файли
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_img:
            await file.download_to_drive(temp_img.name)
            
            img = Image.open(temp_img.name)
            text = pytesseract.image_to_string(img, lang="ukr+eng")
            
            if not text.strip():
                await processing_msg.edit_text("⚠️ Не вдалося розпізнати текст на зображенні.")
                os.remove(temp_img.name)
                return
            
            # Створюємо PDF з підтримкою Unicode
            pdf = FPDF()
            pdf.add_page()
            
            # Спроба використати DejaVu шрифт, якщо є
            font_loaded = False
            try:
                pdf.add_font("DejaVu", "", "fonts/DejaVuSans.ttf", uni=True)
                pdf.set_font("DejaVu", size=12)
                font_loaded = True
            except:
                # Якщо шрифт не знайдено, обробляємо текст
                text = safe_text_for_pdf(text)
                pdf.set_font("Arial", size=12)
                
            pdf.multi_cell(0, 10, text)
            
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_pdf:
                pdf.output(temp_pdf.name)
                
                # Видаляємо повідомлення про обробку
                await processing_msg.delete()
                
                with open(temp_pdf.name, "rb") as f:
                    await update.message.reply_document(
                        InputFile(f, filename="extracted_text.pdf"),
                        caption="📄 PDF створено з розпізнаного тексту"
                    )
                
                # Cleanup
                os.remove(temp_pdf.name)
            
            os.remove(temp_img.name)
            
    except Exception as e:
        logger.error(f"Error processing photo: {e}")
        try:
            await update.message.reply_text("❌ Помилка при обробці зображення. Спробуйте ще раз.")
        except:
            pass

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник текстових повідомлень"""
    try:
        text = update.message.text
        
        if len(text.strip()) == 0:
            await update.message.reply_text("❌ Текст порожній. Надішліть текст для створення PDF.")
            return
        
        # Повідомлення про створення PDF
        processing_msg = await update.message.reply_text("📝 Створюю PDF...")
        
        pdf = FPDF()
        pdf.add_page()
        
        # Спроба використати DejaVu шрифт, якщо є
        font_loaded = False
        try:
            pdf.add_font("DejaVu", "", "fonts/DejaVuSans.ttf", uni=True)
            pdf.set_font("DejaVu", size=12)
            font_loaded = True
        except:
            # Якщо шрифт не знайдено, обробляємо текст
            text = safe_text_for_pdf(text)
            pdf.set_font("Arial", size=12)
            
        pdf.multi_cell(0, 10, text)
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_pdf:
            pdf.output(temp_pdf.name)
            
            # Видаляємо повідомлення про обробку
            await processing_msg.delete()
            
            with open(temp_pdf.name, "rb") as f:
                await update.message.reply_document(
                    InputFile(f, filename="text_document.pdf"),
                    caption="📄 PDF створено з вашого тексту"
                )
            
            # Cleanup
            os.remove(temp_pdf.name)
        
    except Exception as e:
        logger.error(f"Error processing text: {e}")
        try:
            await update.message.reply_text("❌ Помилка при створенні PDF. Спробуйте ще раз.")
        except:
            pass

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник помилок"""
    logger.error(f"Update {update} caused error {context.error}")
    
    if isinstance(context.error, Conflict):
        logger.error("Bot conflict detected. Another instance might be running.")
        # При конфлікті намагаємося зупинити бота
        if application:
            await application.stop()
        sys.exit(1)

def signal_handler(signum, frame):
    """Обробник сигналів для graceful shutdown"""
    logger.info(f"Received signal {signum}. Shutting down...")
    if application and application.running:
        application.stop_running()
    sys.exit(0)

async def main():
    """Головна функція"""
    global application
    
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не встановлено!")
        return
    
    # Налаштування обробників сигналів
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Створення application з додатковими налаштуваннями
    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .connection_pool_size(8)
        .pool_timeout(20.0)
        .connect_timeout(20.0)
        .read_timeout(20.0)
        .write_timeout(20.0)
        .build()
    )
    
    # Додавання обробників
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Додавання обробника помилок
    application.add_error_handler(error_handler)
    
    try:
        logger.info("Запуск бота...")
        
        # Очищення webhook перед запуском polling
        await application.bot.delete_webhook(drop_pending_updates=True)
        
        # Запуск з обробкою помилок
        await application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            close_loop=False
        )
        
    except Conflict as e:
        logger.error(f"Conflict error: {e}")
        logger.error("Another bot instance is running. Stopping...")
        await application.stop()
        sys.exit(1)
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        await application.stop()
        sys.exit(1)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
