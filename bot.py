import os
import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
import re
import asyncio
from aiohttp import web
import json

# Логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "7932585679:AAHD9S-LbNMLdHPYtdFZRwg_2JBu_tdd0ng")
TOGETHER_API_KEY = os.environ.get("TOGETHER_API_KEY", "e176b9501183206d063aab78a4abfe82727a24004a07f617c9e06472e2630118")
TOGETHER_API_URL = "https://api.together.xyz/v1/chat/completions"
PROMPTS_URL = "https://drive.google.com/uc?export=download&id=1byy2KMAGV3Thg0MwH94PMQEjoA3BwqWK"
PORT = int(os.environ.get("PORT", 10000))

app = Application.builder().token(TELEGRAM_BOT_TOKEN).read_timeout(30).write_timeout(30).build()

# Глобальные данные
user_data = {}
user_names = {}
hashtag_cache = {}

# Health check endpoint
async def health_check(request):
    logger.info("Получен запрос на /health")
    return web.Response(text="OK", status=200)

# Функция загрузки промтов с Google Drive
async def get_prompt_from_drive(prompt_name):
    try:
        logger.info(f"Загрузка промта '{prompt_name}' с Google Drive")
        response = requests.get(PROMPTS_URL, timeout=10)
        if response.status_code == 200:
            prompts = json.loads(response.text)
            prompt = prompts.get(prompt_name, "Промт не найден")
            logger.info(f"Промт '{prompt_name}' загружен: {prompt[:50]}...")
            return prompt
        logger.error(f"Ошибка загрузки промтов: {response.status_code} - {response.text}")
        return "Ошибка загрузки промтов"
    except Exception as e:
        logger.error(f"Ошибка при запросе к Google Drive: {e}")
        return "Ошибка загрузки промтов"

# Генерация текста
async def generate_text(user_id, mode):
    logger.info(f"Генерация текста для user_id={user_id}, mode={mode}")
    topic = user_data[user_id].get("topic", "не_указано")
    style = user_data[user_id].get("style", "дружелюбный")
    tone = user_data[user_id].get("tone", "универсальный")
    template = user_data[user_id].get("template", "стандарт")
    niche = user_data[user_id].get("niche", "не_указано")
    client = user_data[user_id].get("client", "не_указано")
    channels = user_data[user_id].get("channels", "не_указано")
    result = user_data[user_id].get("result", "не_указано")
    competitor_keyword = user_data[user_id].get("competitor_keyword", "не_указано")

    base_prompt = await get_prompt_from_drive(mode)
    if "не найден" in base_prompt or "ошибка" in base_prompt.lower():
        logger.error(f"Промт для '{mode}' не загружен")
        return f"Ошибка: промт для '{mode}' не загружен!"

    try:
        full_prompt = base_prompt.format(
            topic=topic.replace('_', ' '),
            style=style,
            tone=tone,
            template=template,
            niche=niche,
            client=client,
            channels=channels,
            result=result,
            competitor_keyword=competitor_keyword
        )
        logger.info(f"Сформирован промт: {full_prompt[:50]}...")
    except KeyError as e:
        logger.error(f"Ошибка в промте: отсутствует параметр {e}")
        return f"Ошибка в промте: отсутствует параметр {e}"

    headers = {"Authorization": f"Bearer {TOGETHER_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "meta-llama/Llama-3-8b-chat-hf",
        "messages": [{"role": "user", "content": full_prompt}],
        "max_tokens": 2000,
        "temperature": 0.5
    }
    try:
        response = requests.post(TOGETHER_API_URL, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            result = response.json()["choices"][0]["message"]["content"].strip()
            logger.info(f"Текст сгенерирован: {result[:50]}...")
            return result
        logger.error(f"Ошибка API Together: {response.status_code} - {response.text}")
        return "Ошибка API"
    except Exception as e:
        logger.error(f"Ошибка генерации текста: {e}")
        return "Сервер не отвечает 😓"

# Генерация идей
async def generate_ideas(topic, style="саркастичный", user_id=None):
    logger.info(f"Генерация идей для topic={topic}, user_id={user_id}")
    niche = user_data.get(user_id, {}).get("niche", "не_указано")
    mode = user_data[user_id].get("mode", "post") if user_id else "post"
    prompt_key = "reels" if mode == "reels" else "ideas"
    base_prompt = await get_prompt_from_drive(prompt_key)
    if "не найден" in base_prompt or "ошибка" in base_prompt.lower():
        logger.error(f"Промт для '{prompt_key}' не загружен")
        return ["1. Ошибка: промт для идей не загружен!"]

    try:
        full_prompt = base_prompt.format(topic=topic, style=style, niche=niche)
        logger.info(f"Сформирован промт для идей: {full_prompt[:50]}...")
    except KeyError as e:
        logger.error(f"Ошибка в промте: отсутствует параметр {e}")
        return [f"1. Ошибка в промте: отсутствует параметр {e}"]

    headers = {"Authorization": f"Bearer {TOGETHER_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "meta-llama/Llama-3-8b-chat-hf",
        "messages": [{"role": "user", "content": full_prompt}],
        "max_tokens": 500,
        "temperature": 0.5  # Более предсказуемый результат
    }
    try:
        response = requests.post(TOGETHER_API_URL, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            raw_text = response.json()["choices"][0]["message"]["content"].strip()
            ideas = [line.strip() for line in raw_text.split("\n") if line.strip()]
            ideas = [re.sub(r'^\d+\.\s*', '', idea) for idea in ideas if len(idea.split()) >= 3][:3]
            if len(ideas) < 3:
                ideas.extend([f"Искры гениальности кончились — попробуй ещё раз!" for _ in range(len(ideas), 3)])
            result = [f"{i+1}. {idea}" for i, idea in enumerate(ideas)]
            logger.info(f"Идеи сгенерированы: {result}")
            return result
        logger.error(f"Ошибка API Together: {response.status_code} - {response.text}")
        return ["1. Ошибка генерации идей 😓"]
    except Exception as e:
        logger.error(f"Ошибка генерации идей: {e}")
        return ["1. Сервер не отвечает 😓"]

# Обработчик сообщений
async def handle_message(update: Update, context: ContextTypes, is_voice=False):
    user_id = update.message.from_user.id
    message = update.message.text.lower().strip() if not is_voice else "голосовое"
    logger.info(f"Получено сообщение от {user_id}: {message}")

    if user_id not in user_data:
        user_data[user_id] = {"preferences": {"topics": [], "styles": []}}
        logger.info(f"Создан новый пользователь: {user_id}")

    base_keyboard = [["Пост", "Сторис", "Reels"], ["Аналитика", "Конкуренты", "А/Б тест"], ["Стратегия/Контент-план", "Хэштеги"]]
    reply_markup = ReplyKeyboardMarkup(base_keyboard, resize_keyboard=True)

    if message == "/start":
        user_data[user_id]["mode"] = "name"
        user_data[user_id]["stage"] = "ask_name"
        await update.message.reply_text("Привет! Как тебя зовут?")
        return

    mode = user_data[user_id].get("mode")
    stage = user_data[user_id].get("stage")
    logger.info(f"Текущая стадия: mode={mode}, stage={stage}")

    if mode == "name" and stage == "ask_name":
        user_names[user_id] = message.capitalize()
        user_data[user_id]["mode"] = "niche"
        user_data[user_id]["stage"] = "ask_niche"
        await update.message.reply_text(f"Отлично, {user_names[user_id]}! В какой нише работаешь?")
    elif mode == "niche" and stage == "ask_niche":
        user_data[user_id]["niche"] = message
        user_data[user_id]["mode"] = "main"
        user_data[user_id]["stage"] = None
        await update.message.reply_text(f"Круто, ниша '{message}'! Что делаем?", reply_markup=reply_markup)
    elif message == "пост":
        user_data[user_id]["mode"] = "post"
        user_data[user_id]["stage"] = "topic"
        await update.message.reply_text(f"О чём написать пост?")
    elif mode == "post" and stage == "topic":
        user_data[user_id]["topic"] = message.replace(" ", "_")
        user_data[user_id]["stage"] = "style"
        await update.message.reply_text(f"Какой стиль текста?", reply_markup=ReplyKeyboardMarkup([["Формальный", "Дружелюбный", "Саркастичный"]], resize_keyboard=True))
    elif mode == "post" and stage == "style":
        user_data[user_id]["style"] = message
        user_data[user_id]["stage"] = "tone"
        await update.message.reply_text(f"Выбери тон для аудитории:", reply_markup=ReplyKeyboardMarkup([["Миллениалы", "Бизнес-аудитория", "Gen Z"]], resize_keyboard=True))
    elif mode == "post" and stage == "tone":
        user_data[user_id]["tone"] = message.lower()
        user_data[user_id]["stage"] = "template"
        await update.message.reply_text(f"Выбери шаблон:", reply_markup=ReplyKeyboardMarkup([["Стандарт", "Объявление"], ["Опрос", "Кейс"]], resize_keyboard=True))
    elif mode == "post" and stage == "template":
        user_data[user_id]["template"] = message
        ideas = await generate_ideas(user_data[user_id]["topic"], user_data[user_id]["style"], user_id)
        user_data[user_id]["stage"] = "ideas"
        await update.message.reply_text(f"Вот идеи:\n" + "\n".join(ideas) + "\nВыбери номер (1, 2, 3)!")
    elif mode == "post" and stage == "ideas":
        if message.isdigit() and 1 <= int(message) <= 3:
            user_data[user_id]["stage"] = "generating"
            response = await generate_text(user_id, "post")
            user_data[user_id]["mode"] = "main"
            user_data[user_id]["stage"] = None
            await update.message.reply_text(f"Вот твой пост:\n{response}", reply_markup=reply_markup)
    elif message == "reels":
        user_data[user_id]["mode"] = "reels"
        user_data[user_id]["stage"] = "topic"
        await update.message.reply_text(f"О чём снять Reels?")
    elif mode == "reels" and stage == "topic":
        user_data[user_id]["topic"] = message.replace(" ", "_")
        ideas = await generate_ideas(user_data[user_id]["topic"], "дружелюбный", user_id)
        user_data[user_id]["stage"] = None
        await update.message.reply_text(f"Вот идеи для Reels:\n" + "\n".join(ideas), reply_markup=reply_markup)
    elif message == "конкуренты":
        user_data[user_id]["mode"] = "competitor_analysis"
        user_data[user_id]["stage"] = "keyword"
        await update.message.reply_text(f"Укажи ключевое слово конкурентов!")
    elif mode == "competitor_analysis" and stage == "keyword":
        user_data[user_id]["competitor_keyword"] = message
        response = await generate_text(user_id, "competitor_analysis")
        user_data[user_id]["stage"] = None
        await update.message.reply_text(f"Анализ конкурентов:\n{response}", reply_markup=reply_markup)
    elif message == "а/б тест":
        user_data[user_id]["mode"] = "ab_testing"
        user_data[user_id]["stage"] = "topic"
        await update.message.reply_text(f"Для чего тестируем заголовки?")
    elif mode == "ab_testing" and stage == "topic":
        user_data[user_id]["topic"] = message.replace(" ", "_")
        response = await generate_text(user_id, "ab_testing")
        user_data[user_id]["stage"] = None
        await update.message.reply_text(f"Вот 3 заголовка:\n{response}\nВыбери номер (1, 2, 3)!", reply_markup=reply_markup)
    elif message == "стратеgia/контент-план":
        user_data[user_id]["mode"] = "strategy"
        user_data[user_id]["stage"] = "topic"
        await update.message.reply_text(f"По какой теме стратегия?")
    elif mode == "strategy" and stage == "topic":
        user_data[user_id]["topic"] = message.replace(" ", "_")
        user_data[user_id]["stage"] = "client"
        await update.message.reply_text(f"Кто целевая аудитория?")
    elif mode == "strategy" and stage == "client":
        user_data[user_id]["client"] = message
        user_data[user_id]["stage"] = "channels"
        await update.message.reply_text(f"Какие каналы продвижения?")
    elif mode == "strategy" and stage == "channels":
        user_data[user_id]["channels"] = message
        user_data[user_id]["stage"] = "result"
        await update.message.reply_text(f"Какой результат нужен?")
    elif mode == "strategy" and stage == "result":
        user_data[user_id]["result"] = message
        response = await generate_text(user_id, "strategy")
        user_data[user_id]["mode"] = "main"
        user_data[user_id]["stage"] = None
        await update.message.reply_text(f"Вот стратегия:\n{response}", reply_markup=reply_markup)
    else:
        await update.message.reply_text(f"Выбери действие!", reply_markup=reply_markup)

# Webhook
async def webhook(request):
    try:
        logger.info("Получен запрос на /webhook")
        data = await request.json()
        logger.info(f"Данные от Telegram: {data}")
        update = Update.de_json(data, app.bot)
        if update:
            logger.info(f"Обработка обновления: {update}")
            await app.process_update(update)
            logger.info("Обновление обработано успешно")
            return web.Response(text="OK", status=200)
        else:
            logger.warning("Получен пустой update")
            return web.Response(text="No update", status=400)
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка декодирования JSON: {e}")
        return web.Response(text="Invalid JSON", status=400)
    except Exception as e:
        logger.error(f"Ошибка в webhook: {e}", exc_info=True)
        return web.Response(text="Error", status=500)

# Запуск
async def main():
    try:
        logger.info("Инициализация приложения...")
        await app.initialize()
        app.add_handler(CommandHandler("start", handle_message))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        web_app = web.Application()
        web_app.router.add_post('/webhook', webhook)
        web_app.router.add_get('/health', health_check)
        logger.info(f"Сервер готов, слушает порт {PORT}")
        webhook_info = await app.bot.get_webhook_info()
        logger.info(f"Текущий webhook: {webhook_info}")
        return web_app
    except Exception as e:
        logger.error(f"Ошибка при запуске: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    logger.info("Запуск бота...")
    try:
        web.run_app(main(), host="0.0.0.0", port=PORT)
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)