import os
import logging
import tempfile
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
        
        # Використовуємо тимчасові файли
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_img:
            await file.download_to_drive(temp_img.name)
            
            img = Image.open(temp_img.name)
            text = pytesseract.image_to_string(img, lang="ukr+eng")
            
            pdf = FPDF()
            pdf.add_page()
            # Використовуємо стандартний шрифт Arial (підтримує Unicode)
            pdf.set_font("Arial", size=12)
            pdf.multi_cell(0, 10, text)
            
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_pdf:
                pdf.output(temp_pdf.name)
                
                with open(temp_pdf.name, "rb") as f:
                    await update.message.reply_document(InputFile(f, filename="text.pdf"))
                
                # Cleanup
                os.remove(temp_pdf.name)
            
            os.remove(temp_img.name)
            
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
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_pdf:
            pdf.output(temp_pdf.name)
            
            with open(temp_pdf.name, "rb") as f:
                await update.message.reply_document(InputFile(f, filename="text.pdf"))
            
            # Cleanup
            os.remove(temp_pdf.name)
        
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
    
    # Використовуємо polling - простіше і надійніше
    logging.info("Запуск бота...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
