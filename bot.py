import os
import logging
import tempfile
import sys
import asyncio # Додано для asyncio.create_task та asyncio.sleep

from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters # Application замість ApplicationBuilder
from telegram.error import Conflict # Інші помилки будуть оброблені загальним Exception

from PIL import Image
import pytesseract
from fpdf import FPDF
from transliterate import translit

# Налаштування логування
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("Змінна середовища BOT_TOKEN не встановлена!")
    sys.exit(1)

# Шлях до Tesseract (зазвичай не потрібно явно вказувати в Docker, якщо він є в PATH)
# pytesseract.pytesseract.tesseract_cmd = "tesseract" # Розкоментуйте, якщо виникають проблеми з пошуком tesseract

# Шлях до шрифту
FONT_PATH = "/app/fonts/DejaVuSans.ttf"

def safe_text_for_pdf(text):
    """Безпечно обробляє текст для PDF, намагаючись зберегти кирилицю."""
    try:
        # Спроба перевірити, чи текст вже підходить для latin-1 (базовий для FPDF без Unicode шрифтів)
        # Це не зовсім коректно, краще завжди використовувати Unicode шрифт
        text.encode('latin-1') 
        return text
    except UnicodeEncodeError:
        # Якщо є кирилиця, яку FPDF не може обробити без Unicode шрифту,
        # і якщо DejaVu не завантажився, транслітеруємо.
        try:
            return translit(text, 'uk', reversed=True)
        except Exception as e:
            logger.warning(f"Помилка транслітерації: {e}. Використовується ASCII з ігноруванням.")
            return text.encode('ascii', 'ignore').decode('ascii')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник команди /start"""
    await update.message.reply_text("👋 Надішли мені зображення, скан або текст, і я згенерую PDF!")

async def process_image_to_pdf(img_path: str, original_update: Update):
    """Допоміжна функція для обробки зображення та створення PDF."""
    try:
        img = Image.open(img_path)
        # Спробуємо розпізнати текст українською та англійською
        text = pytesseract.image_to_string(img, lang="ukr+eng")
        
        if not text.strip():
            await original_update.message.reply_text("⚠️ Не вдалося розпізнати текст на зображенні.")
            return None

        pdf = FPDF()
        pdf.add_page()
        
        font_loaded_successfully = False
        if os.path.exists(FONT_PATH):
            try:
                pdf.add_font("DejaVu", "", FONT_PATH, uni=True)
                pdf.set_font("DejaVu", size=12)
                font_loaded_successfully = True
            except Exception as e:
                logger.warning(f"Не вдалося завантажити шрифт DejaVu: {e}. Використовується стандартний шрифт та транслітерація.")
                # Текст буде оброблено нижче, якщо шрифт не завантажено
        
        if not font_loaded_successfully:
            processed_text = safe_text_for_pdf(text)
            pdf.set_font("Arial", size=12) # Стандартний шрифт FPDF
            pdf.multi_cell(0, 10, processed_text)
        else:
            pdf.multi_cell(0, 10, text) # Використовуємо оригінальний текст з DejaVu
            
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_pdf_file:
            pdf_output_path = temp_pdf_file.name
            pdf.output(pdf_output_path)
        
        return pdf_output_path

    except Exception as e:
        logger.error(f"Помилка під час обробки зображення для PDF: {e}")
        await original_update.message.reply_text("❌ Сталася помилка під час розпізнавання тексту або створення PDF.")
        return None
    finally:
        # Переконуємося, що тимчасовий файл зображення видаляється, якщо він існує
        if 'img_path' in locals() and os.path.exists(img_path):
             try:
                os.remove(img_path)
             except Exception as e_remove:
                logger.error(f"Не вдалося видалити тимчасовий файл зображення {img_path}: {e_remove}")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник фотографій"""
    if not update.message or not update.message.photo:
        return

    processing_msg = await update.message.reply_text("📷 Обробляю зображення...")
    img_download_path = None # Ініціалізуємо змінну
    pdf_path = None # Ініціалізуємо змінну
    
    try:
        photo_file = await update.message.photo[-1].get_file()
        
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_img_file:
            img_download_path = temp_img_file.name
            await photo_file.download_to_drive(img_download_path)

        pdf_path = await process_image_to_pdf(img_download_path, update) 
        # img_download_path буде видалено всередині process_image_to_pdf

        if pdf_path:
            try:
                with open(pdf_path, "rb") as f:
                    await update.message.reply_document(
                        InputFile(f, filename="scan_to_pdf.pdf"),
                        caption="📄 PDF створено з розпізнаного тексту"
                    )
            finally:
                if os.path.exists(pdf_path): # Видаляємо тимчасовий PDF
                    os.remove(pdf_path) 
        
        await processing_msg.delete()

    except Exception as e:
        logger.error(f"Помилка обробки фото: {e}")
        # Перевіряємо, чи processing_msg було успішно надіслано перед спробою редагувати
        if 'processing_msg' in locals() and processing_msg:
            await processing_msg.edit_text("❌ Помилка при обробці зображення. Спробуйте ще раз.")
        else:
            await update.message.reply_text("❌ Помилка при обробці зображення. Спробуйте ще раз.")
    finally:
        # Додаткова перевірка для видалення файлів, якщо вони не були видалені раніше
        if img_download_path and os.path.exists(img_download_path):
            os.remove(img_download_path)
        if pdf_path and os.path.exists(pdf_path):
            os.remove(pdf_path)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник документів (зображень, надісланих як файли)"""
    if not update.message or not update.message.document:
        return

    doc = update.message.document
    img_download_path = None # Ініціалізуємо змінну
    pdf_path = None # Ініціалізуємо змінну

    if doc.mime_type and doc.mime_type.startswith("image/"):
        processing_msg = await update.message.reply_text(f"🖼️ Обробляю надісланий файл ({doc.file_name or 'файл'})...")
        try:
            doc_file = await doc.get_file()
            
            file_extension = os.path.splitext(doc.file_name)[1] if doc.file_name else '.jpg'
            if not file_extension.startswith('.'): # Переконуємося, що розширення починається з точки
                file_extension = '.' + (file_extension if file_extension else 'dat')


            with tempfile.NamedTemporaryFile(suffix=file_extension, delete=False) as temp_doc_file:
                img_download_path = temp_doc_file.name
                await doc_file.download_to_drive(img_download_path)

            pdf_path = await process_image_to_pdf(img_download_path, update)
            # img_download_path буде видалено всередині process_image_to_pdf

            if pdf_path:
                try:
                    with open(pdf_path, "rb") as f:
                        output_filename = "ocr_document.pdf"
                        if doc.file_name:
                            base_name = os.path.splitext(doc.file_name)[0]
                            output_filename = f"{base_name}_ocr.pdf"
                        
                        await update.message.reply_document(
                            InputFile(f, filename=output_filename),
                            caption="📄 PDF створено з розпізнаного тексту документа"
                        )
                finally:
                    if os.path.exists(pdf_path): # Видаляємо тимчасовий PDF
                        os.remove(pdf_path)
            
            await processing_msg.delete()

        except Exception as e:
            logger.error(f"Помилка обробки документа: {e}")
            if 'processing_msg' in locals() and processing_msg:
                 await processing_msg.edit_text("❌ Помилка при обробці файлу. Переконайтесь, що це зображення.")
            else:
                await update.message.reply_text("❌ Помилка при обробці файлу. Переконайтесь, що це зображення.")
        finally:
            # Додаткова перевірка для видалення файлів
            if img_download_path and os.path.exists(img_download_path):
                os.remove(img_download_path)
            if pdf_path and os.path.exists(pdf_path):
                os.remove(pdf_path)
    else:
        await update.message.reply_text("⚠️ Будь ласка, надішліть зображення (як фото або файл) для перетворення в PDF.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник текстових повідомлень для створення PDF"""
    if not update.message or not update.message.text:
        return
        
    text_content = update.message.text.strip()
    
    if not text_content:
        await update.message.reply_text("❌ Текст порожній. Надішліть текст для створення PDF.")
        return
        
    processing_msg = await update.message.reply_text("📝 Створюю PDF з тексту...")
    pdf_output_path = None # Ініціалізуємо змінну
    
    try:
        pdf = FPDF()
        pdf.add_page()
        
        font_loaded_successfully = False
        if os.path.exists(FONT_PATH):
            try:
                pdf.add_font("DejaVu", "", FONT_PATH, uni=True)
                pdf.set_font("DejaVu", size=12)
                font_loaded_successfully = True
            except Exception as e:
                logger.warning(f"Не вдалося завантажити шрифт DejaVu для текстового PDF: {e}. Використовується стандартний шрифт та транслітерація.")

        if not font_loaded_successfully:
            processed_text = safe_text_for_pdf(text_content)
            pdf.set_font("Arial", size=12)
            pdf.multi_cell(0, 10, processed_text)
        else:
            pdf.multi_cell(0, 10, text_content)
            
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_pdf_file:
            pdf_output_path = temp_pdf_file.name
            pdf.output(pdf_output_path)
            
        try:
            with open(pdf_output_path, "rb") as f:
                await update.message.reply_document(
                    InputFile(f, filename="text_to_pdf.pdf"),
                    caption="📄 PDF створено з вашого тексту"
                )
        finally:
            if os.path.exists(pdf_output_path): # Видаляємо тимчасовий PDF
                os.remove(pdf_output_path)
                
        await processing_msg.delete()
        
    except Exception as e:
        logger.error(f"Помилка створення PDF з тексту: {e}")
        if 'processing_msg' in locals() and processing_msg:
            await processing_msg.edit_text("❌ Помилка при створенні PDF з тексту. Спробуйте ще раз.")
        else:
            await update.message.reply_text("❌ Помилка при створенні PDF з тексту. Спробуйте ще раз.")
    finally:
        if pdf_output_path and os.path.exists(pdf_output_path):
            os.remove(pdf_output_path)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Логує помилки, спричинені Update."""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    
    if isinstance(context.error, Conflict):
        logger.critical("Конфлікт! Можливо, інший екземпляр бота вже запущено з цим токеном.")
        if update and hasattr(update, 'message') and hasattr(update.message, 'reply_text'):
             try:
                await update.message.reply_text("Помилка: Конфлікт з іншим екземпляром бота. Зверніться до адміністратора.")
             except Exception as e_reply:
                logger.error(f"Не вдалося надіслати повідомлення про конфлікт: {e_reply}")


async def main() -> None:
    """Запускає бота."""
    
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .connection_pool_size(10) 
        .pool_timeout(30)         
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.IMAGE, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    application.add_error_handler(error_handler)

    try:
        logger.info("Запуск бота...")
        await application.bot.delete_webhook(drop_pending_updates=True)
        logger.info("Вебхук видалено (якщо був).")

        await application.run_polling(
            allowed_updates=Update.ALL_TYPES, 
            drop_pending_updates=True,
        )
        
    except Conflict:
        logger.critical("Критична помилка: Конфлікт. Інший екземпляр бота вже запущено з цим токеном.")
    except Exception as e:
        logger.critical(f"Фатальна помилка під час запуску або роботи бота: {e}", exc_info=True)
    finally:
        logger.info("Бот зупиняється або сталася помилка при запуску.")
        # Перевіряємо, чи application було створено і чи має метод shutdown
        if 'application' in locals() and application and hasattr(application, 'shutdown'):
            try:
                logger.info("Спроба викликати application.shutdown() у блоці finally.")
                await application.shutdown()
                logger.info("application.shutdown() успішно викликано з finally.")
            except Exception as e_shutdown:
                logger.error(f"Помилка під час application.shutdown() у finally: {e_shutdown}")
        else:
            logger.warning("Об'єкт application не був доступний або не має методу shutdown у блоці finally.")
        logger.info("Роботу завершено.")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот зупинено користувачем (KeyboardInterrupt)")
    except RuntimeError as e:
        if "This event loop is already running" in str(e):
            logger.warning("Спроба запустити asyncio.run() в уже запущеному циклі.")
        else:
            logger.critical(f"Критична помилка виконання asyncio: {e}", exc_info=True)
    except Exception as e:
        logger.critical(f"Неперехоплена фатальна помилка: {e}", exc_info=True)
    finally:
        logger.info("Скрипт завершив роботу.")
