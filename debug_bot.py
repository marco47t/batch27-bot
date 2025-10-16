"""Debug version to see what's happening"""
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import config

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def debug_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log all incoming messages"""
    if update.message:
        logger.info(f"📥 Received message: '{update.message.text}' from user {update.effective_user.id}")
        await update.message.reply_text(f"✅ I received: `{update.message.text}`", parse_mode='Markdown')

def main():
    application = Application.builder().token(config.BOT_TOKEN).build()
    
    # Catch ALL messages
    application.add_handler(MessageHandler(filters.ALL, debug_all_messages))
    
    logger.info("🚀 Debug bot started - will echo all messages")
    application.run_polling()

if __name__ == "__main__":
    main()
