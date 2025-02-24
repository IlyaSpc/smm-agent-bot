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

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Настройки API
TELEGRAM_BOT_TOKEN = "7932585679:AAE9_zzdx6_9DocQQbEqPPYsHfzG7gZ-P-w"
TOGETHER_API_KEY = "e176b9501183206d063aab78a4abfe82727a24004a07f617c9e06472e2630118"
TOGETHER_API_URL = "https://api.together.xyz/v1/chat/completions"

# Генерация текста через Together AI API
def generate_text(prompt: str, mode: str):
    if mode == "post":
        full_prompt = (
            "Ты опытный SMM-специалист. Напиши пост на русском языке (8-10 предложений) по теме '{prompt}' для Instagram, ВКонтакте и Telegram. "
            "Пиши ТОЛЬКО на русском языке, любые иностранные слова (английские, чешские и т.д.) категорически запрещены — используй только русские эквиваленты для всех идей, эмоций и терминов! "
            "Если хочешь сказать 'like', пиши 'например', вместо 'her' — 'её', вместо 'conclusion' — 'итог', и так далее. "
            "Стиль: живой, как будто пишешь другу в чате, с уличным вайбом, с эмоциями, строго грамматически правильный (без ошибок в падежах и формах), без лишних деталей и повторов слов, избегай рекламного тона. "
            "Структура: начни с вопроса или факта, расскажи про проблему, предложи решение, кинь пример или эмоцию, закончи ярким призывом к действию, связанным с темой. "
            "Пиши только текст поста."
        ).format(prompt=prompt)
    elif mode == "story":
        full_prompt = (
            "Ты опытный SMM-специалист. Напиши короткий сторителлинг на русском языке (строго 4-6 предложений) по теме '{prompt}' для Instagram, ВКонтакте и Telegram. "
            "Пиши ТОЛЬКО на русском языке, любые иностранные слова запрещены — используй только русские эквиваленты для всех идей, эмоций и терминов! "
            "Если хочешь сказать 'like', пиши 'например', вместо 'her' — 'её', вместо 'conclusion' — 'итог', и так далее. "
            "Стиль: разговорный, как будто пишешь другу в чате, с уличным вайбом, эмоциональный, с метафорами, строго грамматически правильный (без ошибок в падежах и формах), без рекламного тона. "
            "Структура: 1) Захват внимания историей, связанной с '{prompt}', 2) Проблема героя, 3) Решение с примером, 4) Призыв к действию. "
            "Пиши только текст."
        ).format(prompt=prompt)
    elif mode == "strategy":
        full_prompt = (
            "Ты эксперт по клиентогенерации, основываясь на книге Брайана Кэрролла. "
            "Разработай подробную стратегию клиентогенерации на русском языке для бизнеса, связанного с темой '{prompt}' (10-15 предложений). "
            "Пиши ТОЛЬКО на русском языке, любые иностранные слова (английские, чешские и т.д.) категорически запрещены — используй только русские эквиваленты для всех идей и терминов! "
            "Если хочешь сказать 'like', пиши 'например', вместо 'professional' — 'профессиональный', вместо 'regular' — 'регулярно', и так далее. "
            "Стиль: конкретный, пошаговый, с акцентом на детали, строго грамматически правильный (без ошибок в падежах и формах). "
            "Структура: 1) Кто идеальный клиент (подробно: демография, боли, потребности), "
            "2) Воронка продаж (привлечение с конкретными каналами, прогрев с примерами контента, закрытие с тактиками), "
            "3) Автоматизация и инструменты (CRM, рассылки, чат-боты с названиями), 4) Метрики успеха (KPI), 5) Призыв к действию."
        ).format(prompt=prompt)
    elif mode == "image":
        full_prompt = (
            "Ты опытный SMM-специалист. Напиши описание изображения на русском языке (3-5 предложений) по теме '{prompt}' для Instagram, ВКонтакте и Telegram. "
            "Пиши ТОЛЬКО на русском языке, любые иностранные слова запрещены — используй только русские эквиваленты! "
            "Опиши, как выглядит изображение, какие эмоции оно вызывает, и как оно связано с темой '{prompt}'. "
            "Стиль: живой, эмоциональный, с визуальными образами, строго грамматически правильный."
        ).format(prompt=prompt)
    else:
        return "Укажи тип запроса: 'пост про...', 'стори про...', 'стратегия про...', 'изображение про...' или используй 'для' вместо 'про'."

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

# Распознавание голоса
def recognize_voice(audio_file):
    audio = AudioSegment.from_ogg(audio_file)
    wav_file = audio_file.replace(".ogg", ".wav")
    audio.export(wav_file, format="wav")
    recognizer = sr.Recognizer()
    with sr.AudioFile(wav_file) as source:
        audio_data = recognizer.record(source)
    try:
        text = recognizer.recognize_google(audio_data, language="ru-RU")
        os.remove(wav_file)
        return text
    except sr.UnknownValueError:
        os.remove(wav_file)
        return "Не удалось распознать голос, попробуй ещё раз!"
    except sr.RequestError:
        os.remove(wav_file)
        return "Ошибка сервиса распознавания, повтори позже!"

# Обработка текстовых сообщений
async def handle_message(update: Update, context: ContextTypes):
    user_message = update.message.text.strip().lower()
    print(f"Получено сообщение: {user_message}")
    
    if any(x in user_message for x in ["пост про", "напиши пост про", "пост для"]):
        mode = "post"
        topic = re.sub(r"(пост про|напиши пост про|пост для)", "", user_message).strip()
        response = generate_text(topic, mode)
        hashtags = generate_hashtags(topic)
        await update.message.reply_text(f"{response}\n\n{hashtags}")
    elif any(x in user_message for x in ["стори про", "напиши стори", "сторителлинг", "сторис", "стори для"]):
        mode = "story"
        topic = re.sub(r"(стори про|напиши стори|сторителлинг|сторис|стори для)", "", user_message).strip()
        response = generate_text(topic, mode)
        await update.message.reply_text(response)
    elif any(x in user_message for x in ["стратегия про", "напиши стратегию", "стратегия для"]):
        mode = "strategy"
        topic = re.sub(r"(стратегия про|напиши стратегию|стратегия для)", "", user_message).strip()
        response = generate_text(topic, mode)
        await update.message.reply_text(response)
    elif "изображение про" in user_message or "изображение для" in user_message:
        mode = "image"
        topic = re.sub(r"(изображение про|изображение для)", "", user_message).strip()
        response = generate_text(topic, mode)
        await update.message.reply_text(f"Описание изображения:\n{response}")
    else:
        await update.message.reply_text("Укажи тип запроса: 'пост про...', 'стори про...', 'стратегия про...', 'изображение про...' или используй 'для' вместо 'про'.")
    print("Ответ отправлен!")

# Обработка голосовых сообщений
async def handle_voice(update: Update, context: ContextTypes):
    voice_file = await update.message.voice.get_file()
    file_path = f"voice_{update.message.message_id}.ogg"
    await voice_file.download_to_drive(file_path)
    print(f"Получено голосовое сообщение, файл: {file_path}")
    
    text = recognize_voice(file_path)
    print(f"Распознанный текст: {text}")
    os.remove(file_path)
    
    if any(x in text.lower() for x in ["пост про", "напиши пост про", "пост для"]):
        mode = "post"
        topic = re.sub(r"(пост про|напиши пост про|пост для)", "", text.lower()).strip()
        response = generate_text(topic, mode)
        hashtags = generate_hashtags(topic)
        await update.message.reply_text(f"{response}\n\n{hashtags}")
    elif any(x in text.lower() for x in ["стори про", "напиши стори", "сторителлинг", "сторис", "стори для"]):
        mode = "story"
        topic = re.sub(r"(стори про|напиши стори|сторителлинг|сторис|стори для)", "", text.lower()).strip()
        response = generate_text(topic, mode)
        await update.message.reply_text(response)
    elif any(x in text.lower() for x in ["стратегия про", "напиши стратегию", "стратегия для"]):
        mode = "strategy"
        topic = re.sub(r"(стратегия про|напиши стратегию|стратегия для)", "", text.lower()).strip()
        response = generate_text(topic, mode)
        await update.message.reply_text(response)
    elif "изображение про" in text.lower() or "изображение для" in text.lower():
        mode = "image"
        topic = re.sub(r"(изображение про|изображение для)", "", text.lower()).strip()
        response = generate_text(topic, mode)
        await update.message.reply_text(f"Описание изображения:\n{response}")
    else:
        await update.message.reply_text("Укажи тип запроса: 'пост про...', 'стори про...', 'стратегия про...', 'изображение про...' или используй 'для' вместо 'про'.")
    print("Ответ на голос отправлен!")

# Команда /start
async def start(update: Update, context: ContextTypes):
    await update.message.reply_text(
        "Привет, братан! Я твой SMM-кореш, пишу посты, сторисы, стратегии и описываю картинки для Инсты, ВК и Телеги.\n"
        "Кидай запросы, типа: 'пост про кофе', 'стори для города', 'стратегия для художника', 'изображение про зиму'.\n"
        "Голосовые тоже шлю — говори, что надо!"
    )

# Запуск бота
def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    print("✅ Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()