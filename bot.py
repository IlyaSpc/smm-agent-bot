from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
import re
import os
import logging
from aiohttp import web
import speech_recognition as sr
from pydub import AudioSegment

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Настройки API
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "7932585679:AAE9_zzdx6_9DocQQbEqPPYsHfzG7gZ-P-w")
TOGETHER_API_KEY = os.environ.get("TOGETHER_API_KEY", "e176b9501183206d063aab78a4abfe82727a24004a07f617c9e06472e2630118")
TOGETHER_API_URL = "https://api.together.xyz/v1/chat/completions"
PORT = int(os.environ.get("PORT", 8080))

app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# Контекст из книг
BOOK_CONTEXT = """
Книга "Пиши, сокращай" (Максим Ильяхов, Людмила Сарычева):  
Сильный текст — это текст, который помогает читателю решить проблему. Используй информационный стиль: пиши правду, факты и заботься о читателе. Убирай стоп-слова (вводные слова, штампы вроде "команда профессионалов", оценки вроде "качественный"), заменяй их фактами (например, "продукт прошёл 10 тестов" вместо "качественный продукт"). Текст должен быть кратким, ясным и честным, без лишних слов и канцеляризмов. Структурируй текст логически: от простого к сложному, с чёткими абзацами. Главное — уважение к читателю и польза для него.

Книга "Клиентогенерация" (Брайан Кэрролл):  
Клиентогенерация — это система привлечения и удержания клиентов через воронку продаж: привлечение, прогрев, закрытие, удержание. Фокус на идеальном клиенте: понимай его боли, потребности и поведение. Используй контент (статьи, кейсы, вебинары) для создания доверия и прогрева лидов. Автоматизация (CRM, email-маркетинг) помогает не терять лиды и доводить их до покупки. Долгосрочные отношения с клиентами важнее разовых продаж — показывай экспертность и честность.

Книга "Тексты, которым верят" (Пётр Панда):  
Текст должен быть дружелюбным, живым, разговорным, без штампов и пафоса. Начни с цепляющего заголовка по AIDA (внимание → интерес → желание → действие). Захватывай внимание вопросом, проблемой или фактом. Раскрывай боль аудитории, предлагай конкретное решение, закрывай возражения, показывай выгоды через примеры и отзывы. Используй короткие предложения, глаголы действия, метафоры и юмор (где уместно). Завершай чётким призывом к действию, чтобы читатель сказал: «Блин, хочу!» или «Это для меня!».
"""

# Хранилище для ответов пользователей
user_data = {}

# Обработчик ошибок
async def error_handler(update: Update, context: ContextTypes):
    logger.error(f"Произошла ошибка: {context.error}", exc_info=True)
    if update and update.message:
        await update.message.reply_text("Что-то пошло не так. Попробуй ещё раз!")

# Генерация текста через Together AI API
def generate_text(user_id: int, mode: str):
    logger.info(f"Генерация текста для user_id={user_id}, mode={mode}")
    topic = user_data[user_id]["topic"]
    
    if mode in ["post", "story", "image"]:
        goal = user_data[user_id].get("goal", "не указано")
        main_idea = user_data[user_id].get("main_idea", "не указано")
        facts = user_data[user_id].get("facts", "не указано")
        pains = user_data[user_id].get("pains", "не указано")
    else:  # mode == "strategy"
        client = user_data[user_id].get("client", "не указано")
        channels = user_data[user_id].get("channels", "не указано")
        result = user_data[user_id].get("result", "не указано")

    if mode == "post":
        full_prompt = (
            "Ты копирайтер с 10-летним опытом, работающий только на основе книг 'Пиши, сокращай' (Ильяхов, Сарычева), 'Клиентогенерация' (Кэрролл) и 'Тексты, которым верят' (Панда). "
            "Напиши пост на русском языке (10-12 предложений) по теме '{topic}' для социальных сетей. "
            "Цель текста: {goal}. Главная мысль: {main_idea}. Факты: {facts}. Боли и потребности аудитории: {pains}. "
            "Контекст из книг: '{context}'. "
            "Пиши ТОЛЬКО на русском языке, любые иностранные слова категорически запрещены — используй русские эквиваленты (например, 'firsthand' — 'на собственном опыте', 'help us grow' — 'помогают расти', 'family dinner' — 'семейный ужин', 'like' — 'например', 'correct' — 'правильный', 'deserves' — 'заслуживает', 'content' — 'содержание'). "
            "Стиль: дружелюбный, живой, разговорный, с эмоциями, краткий, ясный, без штампов, оценок и повторов, с фактами вместо общих фраз, добавь позитив и лёгкий юмор. "
            "Структура: начни с цепляющего вопроса или факта (AIDA), раскрой проблему аудитории, предложи решение, закрой возражения (например, 'а если нет времени?' или 'а вдруг сложно?'), покажи выгоду через пример, заверши призывом к действию. Пиши только текст поста."
        ).format(topic=topic, goal=goal, main_idea=main_idea, facts=facts, pains=pains, context=BOOK_CONTEXT[:1000])
    elif mode == "story":
        full_prompt = (
            "Ты копирайтер с 10-летним опытом, работающий только на основе книг 'Пиши, сокращай', 'Клиентогенерация' и 'Тексты, которым верят'. "
            "Напиши сторителлинг на русском языке (6-8 предложений) по теме '{topic}' для социальных сетей. "
            "Цель текста: {goal}. Главная мысль: {main_idea}. Факты: {facts}. Боли и потребности аудитории: {pains}. "
            "Контекст из книг: '{context}'. "
            "Пиши ТОЛЬКО на русском языке, любые иностранные слова запрещены — используй русские эквиваленты (например, 'firsthand' — 'на собственном опыте', 'help us grow' — 'помогают расти', 'family dinner' — 'семейный ужин'). "
            "Стиль: живой, эмоциональный, с метафорами, краткий, ясный, разговорный, без штампов, с позитивом и лёгким юмором. "
            "Структура: 1) Начни с истории, которая цепляет (пример из жизни, проблема клиента, факт), 2) Расскажи, почему тебе можно доверять (личная история или миссия), 3) Опиши боль клиента, 4) Покажи, как решение меняет жизнь, 5) Заверши призывом к действию. Пиши только текст сторителлинга."
        ).format(topic=topic, goal=goal, main_idea=main_idea, facts=facts, pains=pains, context=BOOK_CONTEXT[:1000])
    elif mode == "strategy":
        full_prompt = (
            "Ты копирайтер и эксперт по клиентогенерации с 10-летним опытом, работающий только на основе книг 'Пиши, сокращай', 'Клиентогенерация' и 'Тексты, которым верят'. "
            "Разработай стратегию клиентогенерации на русском языке (12-15 предложений) по теме '{topic}'. "
            "Идеальный клиент: {client}. Каналы привлечения: {channels}. Главный результат: {result}. "
            "Контекст из книг: '{context}'. "
            "Пиши ТОЛЬКО на русском языке, любые иностранные слова запрещены — используй русские эквиваленты (например, 'firsthand' — 'на собственном опыте', 'help us grow' — 'помогают расти', 'returns' — 'возврат'). "
            "Стиль: конкретный, пошаговый, с деталями, краткий, ясный, дружелюбный, без штампов, с примерами. "
            "Структура: 1) Кто идеальный клиент (отрасль, боли, потребности), 2) Воронка продаж (привлечение через каналы, прогрев содержанием, закрытие сделки), 3) Инструменты автоматизации (CRM, рассылки, чат-боты), 4) Метрики успеха (KPI), 5) Призыв к действию. Пиши только текст стратегии."
        ).format(topic=topic, client=client, channels=channels, result=result, context=BOOK_CONTEXT[:1000])
    elif mode == "image":
        full_prompt = (
            "Ты копирайтер с 10-летним опытом, работающий только на основе книг 'Пиши, сокращай', 'Клиентогенерация' и 'Тексты, которым верят'. "
            "Напиши описание изображения на русском языке (5-7 предложений) по теме '{topic}' для социальных сетей. "
            "Цель текста: {goal}. Главная мысль: {main_idea}. Факты: {facts}. Боли и потребности аудитории: {pains}. "
            "Контекст из книг: '{context}'. "
            "Пиши ТОЛЬКО на русском языке, любые иностранные слова запрещены — используй русские эквиваленты (например, 'firsthand' — 'на собственном опыте', 'family dinner' — 'семейный ужин'). "
            "Стиль: живой, эмоциональный, с визуальными образами, краткий, ясный, разговорный, без штампов, с позитивом. Опиши изображение, эмоции и связь с темой."
        ).format(topic=topic, goal=goal, main_idea=main_idea, facts=facts, pains=pains, context=BOOK_CONTEXT[:1000])

    logger.info(f"Отправка запроса к Together AI для {mode}")
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
                logger.info("Успешный ответ от Together AI")
                return response.json()["choices"][0]["message"]["content"].strip()
            else:
                logger.error(f"Ошибка API: {response.status_code} - {response.text}")
                return f"Ошибка API: {response.status_code} - {response.text}"
        except (requests.RequestException, TimeoutError) as e:
            logger.warning(f"Попытка {attempt+1} зависла, ждём 5 сек... Ошибка: {e}")
            sleep(5)
    logger.error("Сервер Together AI не отвечает после 3 попыток")
    return "Сервер не отвечает, попробуй позже!"

# Генерация актуальных хэштегов
def generate_hashtags(topic):
    logger.info(f"Генерация хэштегов для темы: {topic}")
    words = topic.split()
    base_hashtags = [f"#{word}" for word in words if len(word) > 2]
    thematic_hashtags = {
        "маркетинг": ["#продвижение", "#бренд", "#реклама", "#smmстратегия", "#маркетолог", "#конверсия"],
        "кофе": ["#кофемания", "#утро", "#напитки", "#кофейня", "#бодрость", "#кофеёк"],
        "собаки": ["#питомцы", "#собачьяжизнь", "#другчеловека", "#животные", "#собакирулят", "#лапы"],
        "чай": ["#чаепитие", "#утро", "#напитки", "#релакс", "#чайнаяпауза", "#уют"],
        "семья": ["#семейныеценности", "#тепло", "#вместе", "#любовь", "#семьямоёвсё", "#родные"],
        "автомобилестроение": ["#авто", "#машины", "#технологии", "#автолюбители", "#движение", "#скорость", "#инновации", "#автомобиль", "#автоистория", "#автодизайн"],
        "дизайнер": ["#дизайн", "#креатив", "#творчество", "#дизайнерскаяжизнь", "#искрыгениальности", "#проекты", "#дизайнвдохновение", "#графика"],
        "музыкант": ["#музыка", "#творчество", "#артист", "#музыкант", "#звук", "#продюсер", "#талант", "#концерт"],
        "искусство": ["#искусство", "#творчество", "#культура", "#арт", "#вдохновение", "#эмоции", "#история"],
        "маркетолог": ["#маркетинг", "#продвижение", "#smm", "#маркетолог", "#бизнес", "#конверсия", "#лиды", "#рост"],
    }
    relevant_tags = []
    for key in thematic_hashtags:
        if key in topic.lower():
            relevant_tags.extend(thematic_hashtags[key])
            break
    if not relevant_tags:
        relevant_tags = ["#соцсети", "#контент", "#идеи", "#полезно", "#жизнь"]
    combined = list(set(base_hashtags + relevant_tags))[:8] + ["#инстаграм", "#вконтакте", "#телеграм"]
    return " ".join(combined)

# Распознавание голоса
async def recognize_voice(file_path):
    logger.info(f"Распознавание голоса для файла: {file_path}")
    try:
        audio = AudioSegment.from_ogg(file_path)
        wav_file = file_path.replace(".ogg", ".wav")
        audio.export(wav_file, format="wav")
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_file) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language="ru-RU")
        os.remove(wav_file)
        logger.info(f"Распознанный текст: {text}")
        return text
    except sr.UnknownValueError:
        logger.warning("Не удалось распознать голос")
        os.remove(wav_file)
        return "Не удалось распознать голос, попробуй ещё раз!"
    except sr.RequestError as e:
        logger.error(f"Ошибка сервиса распознавания: {e}")
        os.remove(wav_file)
        return "Ошибка сервиса распознавания, повтори позже!"
    except Exception as e:
        logger.error(f"Ошибка в recognize_voice: {e}")
        os.remove(wav_file)
        raise

# Обработка сообщений
async def handle_message(update: Update, context: ContextTypes, is_voice=False):
    user_id = update.message.from_user.id
    logger.info(f"Начало обработки сообщения от user_id={user_id}, is_voice={is_voice}")
    
    try:
        if is_voice:
            message = await recognize_voice(f"voice_{update.message.message_id}.ogg")
        else:
            if not update.message.text:
                logger.warning("Сообщение пустое")
                await update.message.reply_text("Сообщение пустое. Напиши что-нибудь!")
                return
            message = update.message.text.strip().lower()
        logger.info(f"Получено сообщение: {message}")
    except Exception as e:
        logger.error(f"Ошибка при получении сообщения: {e}")
        await update.message.reply_text("Не смог обработать сообщение. Попробуй ещё раз!")
        return

    # Проверяем этап диалога
    if user_id not in user_data:
        logger.info("Новый запрос, проверяем тип")
        recognized = False
        if any(x in message for x in ["пост про", "напиши пост про", "пост для"]):
            user_data[user_id] = {"mode": "post", "stage": "goal"}
            topic = re.sub(r"(пост про|напиши пост про|пост для)", "", message).strip()
            recognized = True
        elif any(x in message for x in ["стори про", "напиши стори", "сторителлинг", "сторис", "стори для"]):
            user_data[user_id] = {"mode": "story", "stage": "goal"}
            topic = re.sub(r"(стори про|напиши стори|сторителлинг|сторис|стори для)", "", message).strip()
            recognized = True
        elif any(x in message for x in ["стратегия про", "напиши стратегию", "стратегия для"]):
            user_data[user_id] = {"mode": "strategy", "stage": "client"}
            topic = re.sub(r"(стратегия про|напиши стратегию|стратегия для)", "", message).strip()
            recognized = True
        elif any(x in message for x in ["изображение про", "изображение для"]):
            user_data[user_id] = {"mode": "image", "stage": "goal"}
            topic = re.sub(r"(изображение про|изображение для)", "", message).strip()
            recognized = True

        if recognized:
            user_data[user_id]["topic"] = topic
            logger.info(f"Установлен тип запроса: {user_data[user_id]['mode']}, тема: {topic}")
            if user_data[user_id]["mode"] == "strategy":
                await update.message.reply_text("Кто ваш идеальный клиент? (Опишите аудиторию: возраст, профессия, боли)")
            else:
                await update.message.reply_text("Что должно сделать человек после чтения текста? (Купить, подписаться, обратиться, обсудить)")
        else:
            logger.info("Некорректный запрос")
            await update.message.reply_text("Укажи тип запроса: 'пост про...', 'стори про...', 'стратегия про...', 'изображение про...' или используй 'для' вместо 'про'.")
    elif user_data[user_id]["mode"] != "strategy":
        if user_data[user_id]["stage"] == "goal":
            logger.info("Этап goal")
            user_data[user_id]["goal"] = message
            user_data[user_id]["stage"] = "main_idea"
            await update.message.reply_text("Какая главная мысль должна остаться у читателя?")
        elif user_data[user_id]["stage"] == "main_idea":
            logger.info("Этап main_idea")
            user_data[user_id]["main_idea"] = message
            user_data[user_id]["stage"] = "facts"
            await update.message.reply_text("Какие факты, цифры или примеры могут подтвердить мысль?")
        elif user_data[user_id]["stage"] == "facts":
            logger.info("Этап facts")
            user_data[user_id]["facts"] = message
            user_data[user_id]["stage"] = "pains"
            await update.message.reply_text("Какие боли и потребности аудитории решает этот текст?")
        elif user_data[user_id]["stage"] == "pains":
            logger.info("Этап pains, генерация текста")
            user_data[user_id]["pains"] = message
            mode = user_data[user_id]["mode"]
            response = generate_text(user_id, mode)
            hashtags = generate_hashtags(user_data[user_id]["topic"])
            await update.message.reply_text(f"{response}\n\n{hashtags}")
            logger.info(f"Текст сгенерирован и отправлен для user_id={user_id}")
            del user_data[user_id]
    else:  # mode == "strategy"
        if user_data[user_id]["stage"] == "client":
            logger.info("Этап client")
            user_data[user_id]["client"] = message
            user_data[user_id]["stage"] = "channels"
            await update.message.reply_text("Какие каналы вы хотите использовать для привлечения? (Соцсети, реклама, контент)")
        elif user_data[user_id]["stage"] == "channels":
            logger.info("Этап channels")
            user_data[user_id]["channels"] = message
            user_data[user_id]["stage"] = "result"
            await update.message.reply_text("Какой главный результат вы хотите получить? (Прибыль, клиенты, узнаваемость)")
        elif user_data[user_id]["stage"] == "result":
            logger.info("Этап result, генерация стратегии")
            user_data[user_id]["result"] = message
            mode = user_data[user_id]["mode"]
            response = generate_text(user_id, mode)
            hashtags = generate_hashtags(user_data[user_id]["topic"])
            await update.message.reply_text(f"{response}\n\n{hashtags}")
            logger.info(f"Стратегия сгенерирована и отправлена для user_id={user_id}")
            del user_data[user_id]

# Обработка текстовых сообщений
async def handle_text(update: Update, context: ContextTypes):
    logger.info("Вызов handle_text")
    await handle_message(update, context, is_voice=False)

# Обработка голосовых сообщений
async def handle_voice(update: Update, context: ContextTypes):
    logger.info("Вызов handle_voice")
    voice_file = await update.message.voice.get_file()
    file_path = f"voice_{update.message.message_id}.ogg"
    await voice_file.download_to_drive(file_path)
    logger.info(f"Получено голосовое сообщение, файл: {file_path}")
    await handle_message(update, context, is_voice=True)
    os.remove(file_path)

# Команда /start
async def start(update: Update, context: ContextTypes):
    logger.info("Команда /start")
    await update.message.reply_text(
        "Привет! Я твой SMM-помощник. Могу писать посты, сторис, стратегии и описания изображений для Instagram, ВКонтакте и Telegram.\n"
        "Примеры запросов: 'пост про кофе', 'стори для города', 'стратегия для художника', 'изображение про зиму'.\n"
        "Отвечай на мои вопросы, чтобы получить сильный текст или стратегию, основанные на лучших книгах по копирайтингу и клиентогенерации!"
    )

# Webhook handler
async def webhook(request):
    logger.info("Получен запрос на webhook")
    update = Update.de_json(await request.json(), app.bot)
    if update:
        await app.process_update(update)
    return web.Response(text="OK")

# Настройка и запуск
async def init_app():
    logger.info("Инициализация бота...")
    await app.initialize()
    hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "localhost")
    webhook_url = f"https://{hostname}/webhook"
    await app.bot.set_webhook(url=webhook_url)
    logger.info(f"Webhook установлен: {webhook_url}")

async def main():
    await init_app()
    app.add_error_handler(error_handler)  # Регистрируем обработчик ошибок
    web_app = web.Application()
    web_app.router.add_post('/webhook', webhook)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    return web_app

if __name__ == "__main__":
    logger.info("Запуск бота...")
    web.run_app(main(), host="0.0.0.0", port=PORT)