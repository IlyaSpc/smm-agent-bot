from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
import re
import os
import logging
from time import sleep
import speech_recognition as sr
from pydub import AudioSegment
from fuzzywuzzy import fuzz
import asyncio
from aiohttp import web

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Настройки API
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "7932585679:AAE9_zzdx6_9DocQQbEqPPYsHfzG7gZ-P-w")
TOGETHER_API_KEY = os.environ.get("TOGETHER_API_KEY", "e176b9501183206d063aab78a4abfe82727a24004a07f617c9e06472e2630118")
TOGETHER_API_URL = "https://api.together.xyz/v1/chat/completions"
PORT = int(os.environ.get("PORT", 8080))  # Render даёт порт через переменную PORT

app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# Генерация текста через Together AI API
def generate_text(prompt: str, mode: str):
    if mode == "post":
        full_prompt = (
            "Ты опытный SMM-специалист. Напиши пост на русском языке (8-10 предложений) по теме '{prompt}' для Instagram, ВКонтакте и Telegram. "
            "Пиши ТОЛЬКО на русском языке, любые иностранные слова (английские, чешские и т.д.) категорически запрещены — используй исключительно русские эквиваленты для всех идей, эмоций и терминов! "
            "Если хочешь сказать 'like', пиши 'например', вместо 'correct' — 'правильный', вместо 'her' — 'её', вместо 'conclusion' — 'итог', и так далее. "
            "Стиль: профессиональный, но живой и дружелюбный, с эмоциями, строго грамматически правильный (без ошибок в падежах и формах), без лишних деталей и повторов слов, избегай рекламного тона. "
            "Структура: начни с вопроса или факта, расскажи про проблему, предложи решение, добавь пример или эмоцию, закончи ярким призывом к действию, связанным с темой. "
            "Пиши только текст поста."
        ).format(prompt=prompt)
    # Остальные режимы (story, strategy, image) оставь как есть
    # ... (добавь сюда остальной код generate_text из твоего bot.py)

    headers = {"Authorization": f"Bearer {TOGETHER_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "meta-llama/Llama-3-8b-chat-hf",
        "messages": [{"role": "user", "content": full_prompt}],
        "max_tokens": 1500,
        "temperature": 0.7
    }
    for attempt in range(3):
        try:
            response = requests.post(TOGETHER_API_URL, headers=headers, json=payload, timeout=15)
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"].strip()
            else:
                return f"Ошибка API: {response.status_code} - {response.text}"
        except (requests.RequestException, TimeoutError):
            logging.warning(f"Попытка {attempt+1} зависла, ждём 5 сек...")
            sleep(5)
    return "Сервер не отвечает, попробуй позже!"

# Генерация хэштегов
def generate_hashtags(topic):
    words = topic.split()
    base_hashtags = [f"#{word}" for word in words if len(word) > 2]
    platform_hashtags = ["#инстаграм", "#вконтакте", "#телеграм", "#smm", "#соцсети"]
    return " ".join(base_hashtags[:3] + platform_hashtags)

# Обработка текстовых сообщений
async def handle_message(update: Update, context: ContextTypes):
    user_message = update.message.text.strip().lower()
    print(f"Получено сообщение: {user_message}")
    # Оставь логику обработки как в твоём коде
    if any(x in user_message for x in ["пост про", "напиши пост про", "пост для"]):
        mode = "post"
        topic = re.sub(r"(пост про|напиши пост про|пост для)", "", user_message).strip()
        response = generate_text(topic, mode)
        hashtags = generate_hashtags(topic)
        await update.message.reply_text(f"{response}\n\n{hashtags}")
    # ... (добавь остальную логику handle_message)

# Команда /start
async def start(update: Update, context: ContextTypes):
    await update.message.reply_text(
        "Привет! Я твой SMM-помощник. Могу писать посты, сторис, стратегии и описывать изображения для Instagram, ВКонтакте и Telegram.\n"
        "Примеры запросов: 'пост про кофе', 'стори для города', 'стратегия для художника', 'изображение про зиму'.\n"
        "Голосовые сообщения тоже понимаю!"
    )

# Webhook handler
async def webhook(request):
    update = Update.de_json(await request.json(), app.bot)
    await app.process_update(update)
    return web.Response(text="OK")

# Настройка приложения
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
# Добавь обработку голосовых сообщений, если нужно

# Запуск веб-сервера
async def main():
    print("✅ Бот запущен!")
    await app.bot.set_webhook(url=f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/webhook")
    web_app = web.Application()
    web_app.router.add_post('/webhook', webhook)
    return web_app

if __name__ == "__main__":
    web.run_app(main(), port=PORT)