import os
import logging
import asyncio  # Для работы с асинхронными функциями
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from handlers import start, handle_text  # Импортируем только используемые функции

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
    # Инициализация приложения Telegram Bot API
    app = Application.builder().token(os.getenv("TELEGRAM_BOT_TOKEN")).read_timeout(30).write_timeout(30).build()

    # Добавляем обработчики
    app.add_error_handler(error_handler)  # Обработчик ошибок
    app.add_handler(CommandHandler("start", start))  # Обработчик команды /start
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))  # Обработчик текстовых сообщений

    return app

# Основная точка входа
if __name__ == "__main__":
    app = run()
    # Запускаем бота через webhook
    asyncio.run(app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 80)),  # Порт 80 по умолчанию
        url_path="",
        webhook_url=f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/"
    ))