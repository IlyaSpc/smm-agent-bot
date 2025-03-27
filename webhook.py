import os
import asyncio
from aiohttp import web
from telegram import Update
import logging

logger = logging.getLogger(__name__)

async def webhook(request, application):
    try:
        update = Update.de_json(await request.json(), application.bot)
        await application.process_update(update)
        return web.Response(status=200)
    except Exception as e:
        logger.error(f"Ошибка при обработке вебхука: {e}")
        return web.Response(status=500)

async def on_startup(_, application):
    webhook_url = os.getenv("WEBHOOK_URL")
    if not webhook_url:
        logger.error("WEBHOOK_URL не установлен")
        raise ValueError("WEBHOOK_URL не установлен")
    await application.bot.setWebhook(url=webhook_url)
    logger.info(f"Webhook установлен: {webhook_url}")

async def main(application):
    await application.initialize()
    
    web_app = web.Application()
    web_app.add_routes([web.post('/', lambda request: webhook(request, application))])
    web_app.on_startup.append(lambda app: on_startup(app, application))
    
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 1000)
    await site.start()
    
    await application.start()
    logger.info("Бот запущен с вебхуком на порту 1000")
    await asyncio.Event().wait()