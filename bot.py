import os
import logging
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, filters
from .handlers import start, podpiska, strategiya, goal, audience, period, handle_message, theme, style, template, ideas, edit, cancel
from .webhook import main
from .utils import load_state

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Загружаем состояние при старте
load_state()

token = os.getenv("TELEGRAM_BOT_TOKEN")
if not token:
    logger.error("TELEGRAM_BOT_TOKEN не установлен")
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен")

application = Application.builder().token(token).build()

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("podpiska", podpiska))

strategy_handler = ConversationHandler(
    entry_points=[CommandHandler("strategiya", strategiya)],
    states={
        GOAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, goal)],
        AUDIENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, audience)],
        PERIOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, period)],
    },
    fallbacks=[CommandHandler("cancel", cancel)]
)
application.add_handler(strategy_handler)

conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
    states={
        THEME: [MessageHandler(filters.TEXT & ~filters.COMMAND, theme)],
        STYLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, style)],
        TEMPLATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, template)],
        IDEAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, ideas)],
        EDIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit)],
    },
    fallbacks=[CommandHandler("cancel", cancel)]
)
application.add_handler(conv_handler)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main(application))