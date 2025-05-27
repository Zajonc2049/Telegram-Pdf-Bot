# bot.py

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
    file = await update.message.photo[-1].get_file()
    file_path = await file.download_to_drive()
    logging.info(f"Downloaded image to {file_path}")

    img = Image.open(file_path)
    text = pytesseract.image_to_string(img, lang="ukr+eng")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, text)

    output_path = "output.pdf"
    pdf.output(output_path)

    with open(output_path, "rb") as f:
        await update.message.reply_document(InputFile(f, filename="text.pdf"))

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, text)

    output_path = "text_only.pdf"
    pdf.output(output_path)

    with open(output_path, "rb") as f:
        await update.message.reply_document(InputFile(f, filename="text.pdf"))

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling()

# Create app directory
WORKDIR /app

# Copy project files
COPY bot.py .

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Start bot
CMD ["python", "bot.py"]
