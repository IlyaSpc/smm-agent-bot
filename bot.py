import os
import logging
import asyncio
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from handlers import start, handle_text

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Обработчик ошибок
async def error_handler(update, context):
    logger.error(f"Произошла ошибка: {context.error}", exc_info=True)
    if update and update.message:
        await update.message.reply_text("Ой, что-то пошло не так 😅 Попробуй ещё разок!")

# Функция для запуска бота
def run():
    logger.info("Запуск бота... 🚀")
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("Переменная окружения TELEGRAM_BOT_TOKEN не задана!")
        raise ValueError("TELEGRAM_BOT_TOKEN не задан!")
    
    hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME")
    if not hostname:
        logger.error("Переменная окружения RENDER_EXTERNAL_HOSTNAME не задана!")
        raise ValueError("RENDER_EXTERNAL_HOSTNAME не задан!")
    
    app = Application.builder().token(token).read_timeout(30).write_timeout(30).build()

    # Добавляем обработчики
    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    return app

# Основная точка входа
if __name__ == "__main__":
    app = run()
    asyncio.run(app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 80)),
        url_path="",
        webhook_url=f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/"
    ))