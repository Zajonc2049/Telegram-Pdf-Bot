import os
import logging
from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from PIL import Image
import pytesseract
from fpdf import FPDF

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Ensure tesseract is in PATH if needed (for Docker)
pytesseract.pytesseract.tesseract_cmd = "tesseract"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Надішли мені зображення або скан, і я згенерую PDF з текстом!")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        file = await update.message.photo[-1].get_file()
        file_path = await file.download_to_drive()
        logging.info(f"Downloaded image to {file_path}")
        
        img = Image.open(file_path)
        text = pytesseract.image_to_string(img, lang="ukr+eng")
        
        pdf = FPDF()
        pdf.add_page()
        # Використовуємо стандартний шрифт Arial (підтримує Unicode)
        pdf.set_font("Arial", size=12)
        pdf.multi_cell(0, 10, text)
        
        output_path = "output.pdf"
        pdf.output(output_path)
        
        with open(output_path, "rb") as f:
            await update.message.reply_document(InputFile(f, filename="text.pdf"))
            
        # Cleanup
        os.remove(file_path)
        os.remove(output_path)
        
    except Exception as e:
        logging.error(f"Error processing photo: {e}")
        await update.message.reply_text("❌ Помилка при обробці зображення. Спробуйте ще раз.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text
        
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.multi_cell(0, 10, text)
        
        output_path = "text_only.pdf"
        pdf.output(output_path)
        
        with open(output_path, "rb") as f:
            await update.message.reply_document(InputFile(f, filename="text.pdf"))
            
        # Cleanup
        os.remove(output_path)
        
    except Exception as e:
        logging.error(f"Error processing text: {e}")
        await update.message.reply_text("❌ Помилка при створенні PDF. Спробуйте ще раз.")

def main():
    if not BOT_TOKEN:
        logging.error("BOT_TOKEN не встановлено!")
        return
        
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Автоматично налаштовуємо webhook
    PORT = int(os.environ.get("PORT", 8080))
    RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
    
    if RENDER_URL:
        webhook_url = f"{RENDER_URL}/{BOT_TOKEN}"
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=BOT_TOKEN,
            webhook_url=webhook_url
        )
    else:
        # Локальний режим - використовуємо polling
        logging.info("Запуск в локальному режимі з polling")
        app.run_polling()

if __name__ == '__main__':
    main()
