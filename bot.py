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
        response = requests.get(PROMPTS_URL, timeout=10)
        if response.status_code == 200:
            prompts = json.loads(response.text)
            return prompts.get(prompt_name, "Промт не найден")
        logger.error(f"Ошибка загрузки промтов: {response.status_code} - {response.text}")
        return "Ошибка загрузки промтов"
    except Exception as e:
        logger.error(f"Ошибка при запросе к Google Drive: {e}")
        return "Ошибка загрузки промтов"

# Генерация текста
async def generate_text(user_id, mode):
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
    except KeyError as e:
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
            return response.json()["choices"][0]["message"]["content"].strip()
        return "Ошибка API"
    except Exception as e:
        logger.error(f"Ошибка генерации текста: {e}")
        return "Сервер не отвечает 😓"

# Генерация идей
def generate_ideas(topic, style="саркастичный", user_id=None):
    niche = user_data.get(user_id, {}).get("niche", "не_указано")
    mode = user_data[user_id].get("mode", "post")
    prompt_key = "reels" if mode == "reels" else "ideas"
    base_prompt = asyncio.run(get_prompt_from_drive(prompt_key))
    if "не найден" in base_prompt or "ошибка" in base_prompt.lower():
        return ["1. Ошибка: промт для идей не загружен!"]

    try:
        full_prompt = base_prompt.format(topic=topic, style=style, niche=niche)
    except KeyError as e:
        return [f"1. Ошибка в промте: отсутствует параметр {e}"]

    headers = {"Authorization": f"Bearer {TOGETHER_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "meta-llama/Llama-3-8b-chat-hf",
        "messages": [{"role": "user", "content": full_prompt}],
        "max_tokens": 1000,
        "temperature": 0.7
    }
    try:
        response = requests.post(TOGETHER_API_URL, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            raw_text = response.json()["choices"][0]["message"]["content"].strip()
            ideas = [line.strip() for line in raw_text.split("\n") if line.strip()]
            return [f"{i+1}. {idea}" for i, idea in enumerate(ideas[:3])]
        return ["1. Ошибка генерации идей 😓"]
    except Exception as e:
        logger.error(f"Ошибка генерации идей: {e}")
        return ["1. Сервер не отвечает 😓"]

# Обработчик сообщений
async def handle_message(update: Update, context: ContextTypes, is_voice=False):
    user_id = update.message.from_user.id
    message = update.message.text.lower().strip() if not is_voice else "голосовое"

    if user_id not in user_data:
        user_data[user_id] = {"preferences": {"topics": [], "styles": []}}

    base_keyboard = [["Пост", "Сторис", "Reels"], ["Аналитика", "Конкуренты", "А/Б тест"], ["Стратегия/Контент-план", "Хэштеги"], ["/stats"]]
    reply_markup = ReplyKeyboardMarkup(base_keyboard, resize_keyboard=True)

    if message == "/start":
        user_data[user_id]["mode"] = "name"
        user_data[user_id]["stage"] = "ask_name"
        await update.message.reply_text("Привет! Как тебя зовут?")
        return

    mode = user_data[user_id].get("mode")
    stage = user_data[user_id].get("stage")

    if mode == "name" and stage == "ask_name":
        user_names[user_id] = message.capitalize()
        user_data[user_id]["mode"] = "niche"
        user_data[user_id]["stage"] = "ask_niche"
        await update.message.reply_text(f"Отлично, {user_names[user_id]}! В какой нише работаешь?")
    elif mode == "niche" and stage == "ask_niche":
        user_data[user_id]["niche"] = message
        user_data[user_id]["mode"] = "main"
        await update.message.reply_text(f"Круто, ниша '{message}'! Что делаем?", reply_markup=reply_markup)
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
        ideas = generate_ideas(user_data[user_id]["topic"], user_data[user_id]["style"], user_id)
        user_data[user_id]["stage"] = "ideas"
        await update.message.reply_text(f"Вот идеи:\n" + "\n".join(ideas) + "\nВыбери номер (1, 2, 3)!")
    elif mode == "post" and stage == "ideas":
        if message.isdigit() and 1 <= int(message) <= 3:
            user_data[user_id]["stage"] = "generating"
            response = await generate_text(user_id, "post")
            await update.message.reply_text(f"Вот твой пост:\n{response}", reply_markup=reply_markup)
    elif message == "reels":
        user_data[user_id]["mode"] = "reels"
        user_data[user_id]["stage"] = "topic"
        await update.message.reply_text(f"О чём снять Reels?")
    elif mode == "reels" and stage == "topic":
        user_data[user_id]["topic"] = message.replace(" ", "_")
        ideas = generate_ideas(user_data[user_id]["topic"], "дружелюбный", user_id)
        await update.message.reply_text(f"Вот идеи для Reels:\n" + "\n".join(ideas), reply_markup=reply_markup)
    elif message == "конкуренты":
        user_data[user_id]["mode"] = "competitor_analysis"
        user_data[user_id]["stage"] = "keyword"
        await update.message.reply_text(f"Укажи ключевое слово конкурентов!")
    elif mode == "competitor_analysis" and stage == "keyword":
        user_data[user_id]["competitor_keyword"] = message
        response = await generate_text(user_id, "competitor_analysis")
        await update.message.reply_text(f"Анализ конкурентов:\n{response}", reply_markup=reply_markup)
    elif message == "а/б тест":
        user_data[user_id]["mode"] = "ab_testing"
        user_data[user_id]["stage"] = "topic"
        await update.message.reply_text(f"Для чего тестируем заголовки?")
    elif mode == "ab_testing" and stage == "topic":
        user_data[user_id]["topic"] = message.replace(" ", "_")
        response = await generate_text(user_id, "ab_testing")
        await update.message.reply_text(f"Вот 3 заголовка:\n{response}\nВыбери номер (1, 2, 3)!", reply_markup=reply_markup)
    else:
        await update.message.reply_text(f"Выбери действие!", reply_markup=reply_markup)

# Webhook
async def webhook(request):
    try:
        update = Update.de_json(await request.json(), app.bot)
        await app.process_update(update)
        return web.Response(text="OK", status=200)
    except Exception as e:
        logger.error(f"Ошибка в webhook: {e}")
        return web.Response(text="Error", status=500)

# Запуск
async def main():
    try:
        logger.info("Инициализация приложения...")
        app.add_handler(CommandHandler("start", handle_message))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        web_app = web.Application()
        web_app.router.add_post('/webhook', webhook)
        web_app.router.add_get('/health', health_check)  # Health check endpoint
        logger.info(f"Сервер готов, слушает порт {PORT}")
        return web_app
    except Exception as e:
        logger.error(f"Ошибка при запуске: {e}")
        raise

if __name__ == "__main__":
    logger.info("Запуск бота...")
    try:
        web.run_app(main(), host="0.0.0.0", port=PORT)
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")