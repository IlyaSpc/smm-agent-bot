import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from webhook import main as webhook_main
from handlers import start, handle_message, handle_text, handle_voice

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

async def error_handler(update, context):
    logger.error(f"Произошла ошибка: {context.error}", exc_info=True)
    if update and update.message:
        await update.message.reply_text("Ой, что-то пошло не так 😅 Попробуй ещё разок!")

def run():
    logger.info("Запуск бота... 🚀")
    app = Application.builder().token(os.getenv("TELEGRAM_BOT_TOKEN")).read_timeout(30).write_timeout(30).build()
    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", handle_message))
    app.add_handler(CommandHandler("lang", handle_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    return app

if __name__ == "__main__":
    app = run()
    webhook_main(app)