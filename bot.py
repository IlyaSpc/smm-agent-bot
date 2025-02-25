from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
import re
import os
import logging
from aiohttp import web
import speech_recognition as sr
from pydub import AudioSegment
from time import sleep
import language_tool_python

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

# Инициализация LanguageTool временно отключена
# tool = language_tool_python.LanguageTool('ru', host='https://languagetool.org/api/v2')

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

# Проверка орфографии текста (временно отключена)
def correct_text(text):
    # return tool.correct(text)
    return text  # Возвращаем текст без изменений

# Генерация текста через Together AI API
def generate_text(user_id, mode):
    topic = user_data[user_id].get("topic", "не указано")
    
    if mode in ["post", "story", "image"]:
        goal = user_data[user_id].get("goal", "не указано")
        main_idea = user_data[user_id].get("main_idea", "не указано")
        facts = user_data[user_id].get("facts", "не указано")
        pains = user_data[user_id].get("pains", "не указано")
        idea = user_data[user_id].get("idea", "не указано")
    elif mode == "strategy":
        client = user_data[user_id].get("client", "не указано")
        channels = user_data[user_id].get("channels", "не указано")
        result = user_data[user_id].get("result", "не указано")
    else:  # mode == "analytics"
        reach = user_data[user_id].get("reach", "не указано")
        engagement = user_data[user_id].get("engagement", "не указано")

    if mode == "post":
        full_prompt = (
            "Ты копирайтер с 10-летним опытом, работающий только на основе книг 'Пиши, сокращай' (Ильяхов, Сарычева), 'Клиентогенерация' (Кэрролл) и 'Тексты, которым верят' (Панда). "
            "Напиши пост на русском языке (10-12 предложений) по теме '{topic}' для социальных сетей, используя идею: {idea}. "
            "Цель текста: {goal}. Главная мысль: {main_idea}. Факты: {facts}. Боли и потребности аудитории: {pains}. "
            "Контекст из книг: '{context}'. "
            "Пиши ТОЛЬКО на русском языке, любые иностранные слова запрещены — используй русские эквиваленты (например, 'firsthand' — 'на собственном опыте', 'help us grow' — 'помогают расти', 'family dinner' — 'семейный ужин', 'like' — 'например', 'correct' — 'правильный', 'deserves' — 'заслуживает', 'content' — 'содержание'). "
            "Стиль: дружелюбный, живой, разговорный, с эмоциями, краткий, ясный, без штампов, канцеляризмов (пример: не 'разработать стратегию', а 'настроить план'), без повторов слов вроде 'помогать', 'специалист', 'содержание', с фактами вместо общих фраз, добавь позитив и лёгкий юмор. "
            "Структура: начни с цепляющего вопроса или факта (AIDA), раскрой проблему аудитории, предложи решение, закрой возражения (например, 'а если нет времени?' или 'а вдруг сложно?'), покажи выгоду через пример, заверши призывом к действию. Пиши только текст поста."
        ).format(topic=topic, idea=idea, goal=goal, main_idea=main_idea, facts=facts, pains=pains, context=BOOK_CONTEXT[:1000])
    elif mode == "story":
        full_prompt = (
            "Ты копирайтер с 10-летним опытом, работающий только на основе книг 'Пиши, сокращай', 'Клиентогенерация' и 'Тексты, которым верят'. "
            "Напиши сторителлинг на русском языке (6-8 предложений) по теме '{topic}' для социальных сетей, используя идею: {idea}. "
            "Цель текста: {goal}. Главная мысль: {main_idea}. Факты: {facts}. Боли и потребности аудитории: {pains}. "
            "Контекст из книг: '{context}'. "
            "Пиши ТОЛЬКО на русском языке, любые иностранные слова запрещены — используй русские эквиваленты (например, 'firsthand' — 'на собственном опыте', 'help us grow' — 'помогают расти', 'family dinner' — 'семейный ужин'). "
            "Стиль: живой, эмоциональный, с метафорами, краткий, ясный, разговорный, без штампов, с позитивом и лёгким юмором. "
            "Структура: 1) Начни с истории, которая цепляет (пример из жизни, проблема клиента, факт), 2) Расскажи, почему тебе можно доверять (личная история или миссия), 3) Опиши боль клиента, 4) Покажи, как решение меняет жизнь, 5) Заверши призывом к действию. Пиши только текст сторителлинга."
        ).format(topic=topic, idea=idea, goal=goal, main_idea=main_idea, facts=facts, pains=pains, context=BOOK_CONTEXT[:1000])
    elif mode == "strategy":
        full_prompt = (
            "Ты копирайтер и эксперт по клиентогенерации с 10-летним опытом, работающий только на основе книг 'Пиши, сокращай', 'Клиентогенерация' и 'Тексты, которым верят'. "
            "Разработай стратегию клиентогенерации на русском языке (12-15 предложений) по теме '{topic}'. "
            "Идеальный клиент: {client}. Каналы привлечения: {channels}. Главный результат: {result}. "
            "Контекст из книг: '{context}'. Пример идеальной стратегии: 'Идеальный клиент — владельцы малого бизнеса 30-45 лет, которым нужны клиенты. Привлекаем через рекламу в соцсетях: посты с кейсами и таргет. Прогрев — статьи про рост продаж и вебинары. Закрытие — консультации с предложением услуг. Используем CRM для лидов, рассылки с кейсами, чат-боты для вопросов. Метрики: 50 лидов в месяц, 10% конверсия, возврат инвестиций 200%. Напишите нам — начнём!' "
            "Пиши ТОЛЬКО на русском языке, любые иностранные слова запрещены — используй русские эквиваленты (например, 'firsthand' — 'на собственном опыте', 'help us grow' — 'помогают расти', 'returns' — 'возврат'). "
            "Стиль: конкретный, пошаговый, с деталями, краткий, ясный, дружелюбный, без штампов, с примерами. "
            "Структура: 1) Кто идеальный клиент (отрасль, боли, потребности), 2) Воронка продаж (привлечение через каналы, прогрев содержанием, закрытие сделки), 3) Инструменты автоматизации (CRM, рассылки, чат-боты), 4) Метрики успеха (KPI), 5) Призыв к действию. Пиши только текст стратегии."
        ).format(topic=topic, client=client, channels=channels, result=result, context=BOOK_CONTEXT[:1000])
    elif mode == "image":
        full_prompt = (
            "Ты копирайтер с 10-летним опытом, работающий только на основе книг 'Пиши, сокращай', 'Клиентогенерация' и 'Тексты, которым верят'. "
            "Напиши описание изображения на русском языке (5-7 предложений) по теме '{topic}' для социальных сетей, используя идею: {idea}. "
            "Цель текста: {goal}. Главная мысль: {main_idea}. Факты: {facts}. Боли и потребности аудитории: {pains}. "
            "Контекст из книг: '{context}'. "
            "Пиши ТОЛЬКО на русском языке, любые иностранные слова запрещены — используй русские эквиваленты (например, 'firsthand' — 'на собственном опыте', 'family dinner' — 'семейный ужин'). "
            "Стиль: живой, эмоциональный, с визуальными образами, краткий, ясный, разговорный, без штампов, с позитивом. Опиши изображение, эмоции и связь с темой."
        ).format(topic=topic, idea=idea, goal=goal, main_idea=main_idea, facts=facts, pains=pains, context=BOOK_CONTEXT[:1000])
    elif mode == "analytics":
        full_prompt = (
            "Ты эксперт по SMM с 10-летним опытом, работающий только на основе книг 'Пиши, сокращай', 'Клиентогенерация' и 'Тексты, которым верят'. "
            "Проанализируй данные аналитики для темы '{topic}' и дай рекомендации (5-7 предложений). "
            "Охват: {reach}. Вовлечённость (лайки, комментарии): {engagement}. "
            "Контекст из книг: '{context}'. "
            "Пиши ТОЛЬКО на русском языке, любые иностранные слова запрещены — используй русские эквиваленты (например, 'returns' — 'возврат', 'engagement' — 'вовлечённость'). "
            "Стиль: конкретный, ясный, дружелюбный, с примерами улучшений. Пиши только текст рекомендаций."
        ).format(topic=topic, reach=reach, engagement=engagement, context=BOOK_CONTEXT[:1000])

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
                corrected_text = correct_text(response.json()["choices"][0]["message"]["content"].strip())
                return corrected_text
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
        "самолёты": ["#самолёты", "#авиация", "#полёты", "#технологии", "#путешествия", "#небо", "#пилот"],
        "футбол": ["#футбол", "#спорт", "#игра", "#болельщики", "#матч", "#гол"],
        "хоккей": ["#хоккей", "#спорт", "#лед", "#игра", "#болельщики", "#шайба"]
    }
    relevant_tags = []
    for key in thematic_hashtags:
        if key in topic.lower():
            relevant_tags.extend(thematic_hashtags[key])
            break
    if not relevant_tags:
        relevant_tags = ["#соцсети", "#содержание", "#идеи", "#полезно", "#жизнь"]
    
    combined = list(set(base_hashtags + relevant_tags))
    combined.sort(key=lambda x: (len(x), x in topic.lower()), reverse=True)
    final_tags = combined[:8] + ["#инстаграм", "#вконтакте", "#телеграм"]
    return " ".join(final_tags)

# Генерация идей для контента
def generate_ideas(topic):
    logger.info(f"Генерация идей для темы: {topic}")
    prompt = (
        "Ты креативный SMM-специалист, работающий для русскоязычной аудитории. "
        "Придумай 3-5 идей для контента по теме '{topic}'. "
        "Идеи должны быть актуальными для социальных сетей в 2025 году (тренды: Reels, карусели, AMA), конкретными и интересными. "
        "Пиши ТОЛЬКО на русском языке, любые иностранные слова запрещены — используй только русские эквиваленты. "
        "Пример для темы 'кофе': 1) Reels с процессом заваривания утреннего напитка, 2) Карусель с фактами о разных сортах, 3) AMA про любимый напиток подписчиков. "
        "Верни только список идей в формате: 1) ..., 2) ..., 3) ... и т.д. "
        "Убедись, что весь текст на русском языке, без исключений!"
    ).format(topic=topic)
    
    headers = {"Authorization": f"Bearer {TOGETHER_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "meta-llama/Llama-3-8b-chat-hf",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 500,
        "temperature": 0.9
    }
    for attempt in range(3):
        try:
            response = requests.post(TOGETHER_API_URL, headers=headers, json=payload, timeout=10)
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"].strip().split("\n")
            else:
                logger.error(f"Ошибка API при генерации идей: {response.status_code} - {response.text}")
        except (requests.RequestException, TimeoutError) as e:
            logger.warning(f"Попытка {attempt+1} зависла, ждём 5 сек... Ошибка: {e}")
            sleep(5)
    return ["1) Идея не сгенерировалась, попробуй ещё раз!"]

# Распознавание голосовых сообщений
async def recognize_voice(file_path):
    logger.info(f"Распознавание голосового сообщения: {file_path}")
    audio = AudioSegment.from_ogg(file_path)
    audio.export("temp.wav", format="wav")
    recognizer = sr.Recognizer()
    with sr.AudioFile("temp.wav") as source:
        audio_data = recognizer.record(source)
        try:
            text = recognizer.recognize_google(audio_data, language="ru-RU")
            logger.info(f"Распознанный текст: {text}")
            os.remove("temp.wav")
            return text
        except sr.UnknownValueError:
            logger.error("Не удалось распознать голос")
            os.remove("temp.wav")
            return "Не понял, что ты сказал. Повтори!"
        except sr.RequestError as e:
            logger.error(f"Ошибка сервиса распознавания: {e}")
            os.remove("temp.wav")
            return "Ошибка сервиса распознавания. Попробуй ещё раз!"

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

    # Проверяем, новый ли это запрос
    new_request = any(x in message for x in ["пост про", "напиши пост про", "пост для",
                                            "стори про", "напиши стори", "сторителлинг", "сторис", "стори для",
                                            "стратегия про", "напиши стратегию", "стратегия для",
                                            "изображение про", "изображение для",
                                            "аналитика", "анализируй"])
    
    if new_request or user_id not in user_data:
        logger.info("Новый запрос, проверяем тип")
        if user_id in user_data:
            del user_data[user_id]  # Очищаем старые данные для нового запроса
        
        recognized = False
        if any(x in message for x in ["пост про", "напиши пост про", "пост для"]):
            user_data[user_id] = {"mode": "post", "stage": "ideas"}
            topic = re.sub(r"(пост про|напиши пост про|пост для)", "", message).strip()
            recognized = True
        elif any(x in message for x in ["стори про", "напиши стори", "сторителлинг", "сторис", "стори для"]):
            user_data[user_id] = {"mode": "story", "stage": "ideas"}
            topic = re.sub(r"(стори про|напиши стори|сторителлинг|сторис|стори для)", "", message).strip()
            recognized = True
        elif any(x in message for x in ["стратегия про", "напиши стратегию", "стратегия для"]):
            user_data[user_id] = {"mode": "strategy", "stage": "client"}
            topic = re.sub(r"(стратегия про|напиши стратегию|стратегия для)", "", message).strip()
            recognized = True
        elif any(x in message for x in ["изображение про", "изображение для"]):
            user_data[user_id] = {"mode": "image", "stage": "ideas"}
            topic = re.sub(r"(изображение про|изображение для)", "", message).strip()
            recognized = True
        elif "аналитика" in message or "анализируй" in message:
            user_data[user_id] = {"mode": "analytics", "stage": "reach"}
            topic = re.sub(r"(аналитика|анализируй|про|для)", "", message).strip()
            recognized = True

        if recognized:
            user_data[user_id]["topic"] = topic
            logger.info(f"Установлен тип запроса: {user_data[user_id]['mode']}, тема: {topic}")
            if user_data[user_id]["mode"] == "strategy":
                await update.message.reply_text("Кто ваш идеальный клиент? (Опишите аудиторию: возраст, профессия, боли)")
            elif user_data[user_id]["mode"] == "analytics":
                await update.message.reply_text("Какой охват у вашего контента? (Например, 500 просмотров)")
            else:
                ideas = generate_ideas(topic)
                await update.message.reply_text(f"Вот идеи для '{topic}':\n" + "\n".join(ideas) + "\nВыбери номер идеи (1, 2, 3...) или напиши свою!")
        else:
            logger.info("Некорректный запрос")
            await update.message.reply_text("Укажи тип запроса: 'пост про...', 'стори про...', 'стратегия про...', 'изображение про...', 'аналитика для...'.")
    else:
        current_topic = user_data[user_id]["topic"]
        if current_topic in message and user_data[user_id]["mode"] != "strategy" and user_data[user_id]["stage"] != "ideas":
            logger.info(f"Продолжаем текущий запрос с темой: {current_topic}")
        elif user_data[user_id]["mode"] == "analytics":
            if user_data[user_id]["stage"] == "reach":
                logger.info("Этап reach")
                user_data[user_id]["reach"] = message
                user_data[user_id]["stage"] = "engagement"
                await update.message.reply_text("Какая вовлечённость? (Например, 20 лайков, 5 комментариев)")
            elif user_data[user_id]["stage"] == "engagement":
                logger.info("Этап engagement, генерация аналитики")
                user_data[user_id]["engagement"] = message
                mode = user_data[user_id]["mode"]
                response = generate_text(user_id, mode)
                await update.message.reply_text(response)
                logger.info(f"Аналитика сгенерирована и отправлена для user_id={user_id}")
                del user_data[user_id]
        elif user_data[user_id]["mode"] != "strategy":
            if user_data[user_id]["stage"] == "ideas":
                logger.info("Этап ideas")
                user_data[user_id]["idea"] = message
                user_data[user_id]["stage"] = "goal"
                await update.message.reply_text("Что должно сделать человек после чтения текста? (Купить, подписаться, обратиться, обсудить)")
            elif user_data[user_id]["stage"] == "goal":
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
                try:
                    await update.message.reply_text(f"{response}\n\n{hashtags}")
                    logger.info(f"Текст успешно отправлен для user_id={user_id}")
                except Exception as e:
                    logger.error(f"Ошибка отправки текста: {e}")
                logger.info(f"Текст сгенерирован для user_id={user_id}")
                del user_data[user_id]
        else:  # mode == "strategy"
            if user_data[user_id]["stage"] == "client":
                logger.info("Этап client")
                user_data[user_id]["client"] = message
                user_data[user_id]["stage"] = "channels"
                await update.message.reply_text("Какие каналы вы хотите использовать для привлечения? (Соцсети, реклама, содержание)")
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
                try:
                    await update.message.reply_text(f"{response}\n\n{hashtags}")
                    logger.info(f"Стратегия успешно отправлена для user_id={user_id}")
                except Exception as e:
                    logger.error(f"Ошибка отправки стратегии: {e}")
                logger.info(f"Стратегия сгенерирована для user_id={user_id}")
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
        "Привет! Я твой SMM-помощник. Могу писать посты, сторис, стратегии, описания изображений и анализировать данные для Instagram, ВКонтакте и Telegram.\n"
        "Примеры запросов: 'пост про кофе', 'стори для города', 'стратегия для художника', 'аналитика для музыканта'.\n"
        "Отвечай на мои вопросы, чтобы получить сильный текст, стратегию или рекомендации!"
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
    app.add_error_handler(error_handler)
    web_app = web.Application()
    web_app.router.add_post('/webhook', webhook)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    return web_app

if __name__ == "__main__":
    logger.info("Запуск бота...")
    web.run_app(main(), host="0.0.0.0", port=PORT)