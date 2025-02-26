from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
import re
import os
import logging
from aiohttp import web
import speech_recognition as sr
from pydub import AudioSegment
from time import sleep
from fpdf import FPDF
import asyncio
import random

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Настройки API
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "7932585679:AAHD9S-LbNMLdHPYtdFZRwg_2JBu_tdd0ng")
TOGETHER_API_KEY = os.environ.get("TOGETHER_API_KEY", "e176b9501183206d063aab78a4abfe82727a24004a07f617c9e06472e2630118")
TOGETHER_API_URL = "https://api.together.xyz/v1/chat/completions"
LANGUAGE_TOOL_URL = "https://languagetool.org/api/v2/check"
PORT = int(os.environ.get("PORT", 10000))  # Указываем порт 10000 для Render

# Увеличиваем таймаут для Telegram до 30 секунд
app = Application.builder().token(TELEGRAM_BOT_TOKEN).read_timeout(30).write_timeout(30).build()

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

# Проверка орфографии текста через публичный API LanguageTool
def correct_text(text):
    payload = {
        "text": text,
        "language": "ru"
    }
    try:
        response = requests.post(LANGUAGE_TOOL_URL, data=payload, timeout=5)
        if response.status_code == 200:
            data = response.json()
            corrected_text = text
            offset = 0
            for match in data.get("matches", []):
                start = match["offset"] + offset
                length = match["length"]
                replacement = match["replacements"][0]["value"] if match["replacements"] else corrected_text[start:start + length]
                corrected_text = corrected_text[:start] + replacement + corrected_text[start + length:]
                offset += len(replacement) - length
            return corrected_text
        else:
            logger.error(f"Ошибка LanguageTool API: {response.status_code} - {response.text}")
            return text
    except (requests.RequestException, TimeoutError) as e:
        logger.error(f"Ошибка запроса к LanguageTool API: {e}")
        return text

# Распознавание голосовых сообщений
async def recognize_voice(file_path):
    try:
        audio = AudioSegment.from_ogg(file_path)
        wav_path = file_path.replace(".ogg", ".wav")
        audio.export(wav_path, format="wav")
        
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language="ru-RU")
        os.remove(wav_path)
        logger.info(f"Распознан текст из голосового сообщения: {text}")
        return text.lower()
    except sr.UnknownValueError:
        logger.error("Не удалось распознать голосовое сообщение")
        return "Не разобрал, что ты сказал. Попробуй ещё раз!"
    except Exception as e:
        logger.error(f"Ошибка распознавания голоса: {e}")
        return "Ошибка при распознавании голоса. Попробуй ещё раз!"

# Создание PDF из текста
def create_pdf(text, filename="strategy.pdf"):
    try:
        if not os.path.exists("DejaVuSans.ttf"):
            logger.error("Шрифт DejaVuSans.ttf не найден!")
            raise FileNotFoundError("Шрифт DejaVuSans.ttf не найден!")
        pdf = FPDF()
        pdf.add_page()
        pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
        pdf.set_font("DejaVu", size=12)
        pdf.multi_cell(0, 10, text)
        pdf.output(filename)
        logger.info(f"PDF успешно создан: {filename}")
        return filename
    except Exception as e:
        logger.error(f"Ошибка при создании PDF: {e}", exc_info=True)
        raise

# Генерация разнообразных идей для постов, сторис и т.д.
def generate_ideas(topic):
    idea_pool = [
        f"Расскажи, как {topic} решает твои повседневные заботы.",
        f"Поделись необычным фактом о {topic}, который мало кто знает.",
        f"Покажи через пример, как {topic} делает жизнь ярче.",
        f"Объясни, почему {topic} — это то, что нужно каждому.",
        f"Сравни {topic} с чем-то неожиданным и цепляющим.",
        f"Дай простой совет, как {topic} улучшает день.",
        f"Расскажи историю, где {topic} стал спасением.",
        f"Раскрой секрет, как {topic} помогает в незаметных мелочах.",
        f"Покажи, как {topic} мотивирует на большие перемены.",
        f"Развей популярный миф о {topic} с помощью фактов.",
        f"Опиши чувства, которые вызывает {topic} у тебя и других.",
        f"Предложи, как сделать {topic} частью утреннего ритуала.",
        f"Свяжи {topic} с чем-то актуальным и трендовым.",
        f"Назови три причины попробовать {topic} прямо сейчас.",
        f"Расскажи, как {topic} спасает от хаоса и суеты."
    ]
    selected_ideas = random.sample(idea_pool, 3)  # Выбираем 3 случайные уникальные идеи
    return [f"{i+1}. {idea}" for i, idea in enumerate(selected_ideas)]

# Генерация текста через Together AI API
def generate_text(user_id, mode):
    topic = user_data[user_id].get("topic", "не указано")
    full_prompt = ""  # Инициализируем пустой промпт
    
    if mode in ["post", "story", "image"]:
        goal = user_data[user_id].get("goal", "привлечение")
        main_idea = user_data[user_id].get("main_idea", "показать пользу темы")
        facts = user_data[user_id].get("facts", "основаны на реальных примерах")
        pains = user_data[user_id].get("pains", "нехватка времени и информации")
        idea = user_data[user_id].get("idea", "не указано")

        if mode == "post":
            full_prompt = (
                "Ты копирайтер с 10-летним опытом, работающий только на основе книг 'Пиши, сокращай', 'Клиентогенерация' и 'Тексты, которым верят'. "
                "Напиши пост на русском языке (10-12 предложений) по теме '{topic}' для социальных сетей, используя идею: {idea}. "
                "Цель текста: {goal}. Главная мысль: {main_idea}. Факты: {facts}. Боли и потребности аудитории: {pains}. "
                "Контекст из книг: '{context}'. "
                "Пиши исключительно на русском языке, любые иностранные слова запрещены — используй только русские эквиваленты (например, 'firsthand' — 'из первых рук', 'like' — 'например'). "
                "Пример текста: 'Хотите больше клиентов? Узнайте, как простые шаги помогают вырасти!' "
                "Стиль: дружелюбный, живой, разговорный, с эмоциями, краткий, ясный, без штампов, канцеляризмов, с фактами вместо общих фраз, добавь позитив и лёгкий юмор. "
                "Структура: начни с цепляющего вопроса или факта (AIDA), раскрой проблему аудитории, предложи решение, закрой возражения, покажи выгоду через пример, заверши призывом к действию. Пиши только текст поста."
            ).format(topic=topic, idea=idea, goal=goal, main_idea=main_idea, facts=facts, pains=pains, context=BOOK_CONTEXT[:1000])
        elif mode == "story":
            full_prompt = (
                "Ты копирайтер с 10-летним опытом, работающий только на основе книг 'Пиши, сокращай', 'Клиентогенерация' и 'Тексты, которым верят'. "
                "Напиши сторителлинг на русском языке (6-8 предложений) по теме '{topic}' для социальных сетей, используя идею: {idea}. "
                "Цель текста: {goal}. Главная мысль: {main_idea}. Факты: {facts}. Боли и потребности аудитории: {pains}. "
                "Контекст из книг: '{context}'. "
                "Пиши исключительно на русском языке, любые иностранные слова запрещены — используй русские эквиваленты (например, 'firsthand' — 'из первых рук'). "
                "Стиль: живой, эмоциональный, с метафорами, краткий, ясный, разговорный, без штампов, с позитивом и лёгким юмором. "
                "Структура: начни с истории, которая цепляет, расскажи, почему тебе можно доверять, опиши боль клиента, покажи, как решение меняет жизнь, заверши призывом к действию. Пиши только текст сторителлинга."
            ).format(topic=topic, idea=idea, goal=goal, main_idea=main_idea, facts=facts, pains=pains, context=BOOK_CONTEXT[:1000])
        elif mode == "image":
            full_prompt = (
                "Ты копирайтер с 10-летним опытом, работающий только на основе книг 'Пиши, сокращай', 'Клиентогенерация' и 'Тексты, которым верят'. "
                "Напиши описание изображения на русском языке (5-7 предложений) по теме '{topic}' для социальных сетей, используя идею: {idea}. "
                "Цель текста: {goal}. Главная мысль: {main_idea}. Факты: {facts}. Боли и потребности аудитории: {pains}. "
                "Контекст из книг: '{context}'. "
                "Пиши исключительно на русском языке, любые иностранные слова запрещены — используй русские эквиваленты (например, 'firsthand' — 'из первых рук'). "
                "Стиль: живой, эмоциональный, с визуальными образами, краткий, ясный, разговорный, без штампов, с позитивом. Опиши изображение, эмоции и связь с темой."
            ).format(topic=topic, idea=idea, goal=goal, main_idea=main_idea, facts=facts, pains=pains, context=BOOK_CONTEXT[:1000])
    elif mode == "strategy":
        client = user_data[user_id].get("client", "не указано")
        channels = user_data[user_id].get("channels", "не указано")
        result = user_data[user_id].get("result", "не указано")
        full_prompt = (
            "Ты профессиональный маркетолог и SMM-специалист с 10-летним опытом, работающий на основе книг 'Пиши, сокращай', 'Клиентогенерация' и 'Тексты, которым верят'. "
            "Разработай стратегию клиентогенерации на русском языке по теме '{topic}'. "
            "Целевая аудитория: {client}. Каналы привлечения: {channels}. Главный результат: {result}. "
            "Контекст из книг: '{context}'. "
            "Пиши исключительно на русском языке, категорически запрещено использовать любые иностранные слова (английские, испанские, французские, немецкие и т.д.) — заменяй их русскими эквивалентами (например, 'aged' — 'в возрасте', 'thoughts' — 'мысли', 'confidence' — 'уверенность', 'find' — 'найти', 'spends' — 'проводит', 'build' — 'развить', 'semaine' — 'неделя', 'professional' — 'профессиональный', 'guidance' — 'поддержка', 'consultation' — 'консультация'). "
            "Пример текста: 'Люди 20-30 лет хотят улучшить здоровье. Они ищут мотивацию и боятся тратить время зря.' "
            "Текст должен содержать только русские буквы и символы, любые не-русские слова недопустимы даже в промежуточных результатах. "
            "Стиль: конкретный, пошаговый, дружелюбный, с примерами, без штампов, с фактами. "
            "Выполни следующие задачи: "
            "1) Дай глубокое и подробное описание целевой аудитории: возраст, пол, профессия, интересы, поведение, привычки. "
            "2) Перечисли 'точки боли' аудитории в формате списка (5-7 пунктов). "
            "3) Перечисли желания аудитории в формате списка (5-7 пунктов). "
            "4) Опиши момент покупки: эмоции (например, отчаяние, надежда), желания (например, найти решение), барьеры (например, страх потратить деньги впустую, недоверие к мастерам), добавь больше деталей и эмоций, связанных с темой '{topic}', исключи нерелевантные услуги. "
            "5) Создай 5 реалистичных пользовательских персонажей, представляющих ЦА. Для каждого укажи: "
            "   - Имя "
            "   - Демография (возраст, пол, род занятий, местоположение) "
            "   - Основные цели и мотивации "
            "   - Основные проблемы и боли "
            "   - Повседневные занятия "
            "   - Цитата персоны. "
            "Персонажи должны быть разными, реалистичными, основанными на ЦА и теме. "
            "6) После каждого персонажа добавь подзаголовок 'Как делать!' и предложи уникальный план действий, как мне, как SMM-специалисту, превратить эту персону в клиента бизнеса. Какие способы взаимодействия я могу использовать? Как продавать через соцсети? Распиши по шагам (3-5 шагов) действия, чтобы продать сегменту этой персоны услуги, связанные с темой '{topic}', учитывая её профессию и боли. Планы должны быть уникальными для каждой персоны, используй разные форматы (посты, короткие видео, сторис, вебинары, карусели, прямые эфиры) и соцсети (Instagram, ВКонтакте, Telegram), избегая повторений. "
            "7) Заверши общим призывом к действию для всей стратегии, добавь пример метрик: количество лидов, конверсия, доход (например, 1000 лидов, 20% конверсия, 50000 рублей дохода). Пиши только текст стратегии, включи все 5 персонажей полностью."
        ).format(topic=topic, client=client, channels=channels, result=result, context=BOOK_CONTEXT[:1000])
    elif mode == "content_plan":
        frequency = user_data[user_id].get("frequency", "не указано")
        client = user_data[user_id].get("client", "не указано")
        channels = user_data[user_id].get("channels", "не указано")
        full_prompt = (
            "Ты SMM-специалист с 10-летним опытом, работающий на основе книг 'Пиши, сокращай', 'Клиентогенерация' и 'Тексты, которым верят'. "
            "Составь контент-план на русском языке для продвижения '{topic}' в социальных сетях с 27 февраля 2025 года. "
            "Целевая аудитория: {client}. Каналы: {channels}. Частота публикаций: {frequency}. "
            "Контекст из книг: '{context}'. "
            "Пиши исключительно на русском языке, категорически запрещено использовать любые иностранные слова — заменяй их русскими эквивалентами (например, 'post' — 'пост', 'reels' — 'короткие видео', 'confidence' — 'уверенность', 'semaine' — 'неделя', 'build' — 'развить', 'week' — 'неделя', 'guidance' — 'поддержка', 'cope' — 'справляться', 'relationship' — 'отношения', 'gratitude' — 'благодарность'). "
            "Пример текста: '27 февраля 2025, 10:00 - пост: Как справляться со стрессом? Советы мастера помогут вам!' "
            "Составь план на 2 недели, укажи: "
            "1) Дату и время публикации для каждого поста или видео, начиная с 27 февраля 2025 года. "
            "2) Тип контента (пост, короткое видео). "
            "3) Краткое описание (2-3 предложения) с идеей контента, связанной с темой '{topic}'. "
            "4) Цель (привлечение, прогрев, продажа). "
            "Если частота публикаций — '2 поста и 3 видео в неделю', создай ровно 4 поста и 6 коротких видео за 2 недели, распредели контент равномерно, используй только посты и короткие видео. Пиши только текст контент-плана."
        ).format(topic=topic, client=client, channels=channels, frequency=frequency, context=BOOK_CONTEXT[:1000])
    elif mode == "analytics":
        reach = user_data[user_id].get("reach", "не указано")
        engagement = user_data[user_id].get("engagement", "не указано")
        full_prompt = (
            "Ты SMM-специалист с 10-летним опытом, работающий на основе книг 'Пиши, сокращай', 'Клиентогенерация' и 'Тексты, которым верят'. "
            "Составь краткий анализ на русском языке по теме '{topic}' для социальных сетей. "
            "Охват: {reach}. Вовлечённость: {engagement}. "
            "Контекст из книг: '{context}'. "
            "Пиши исключительно на русском языке, любые иностранные слова запрещены — используй русские эквиваленты (например, 'reach' — 'охват', 'engagement' — 'вовлечённость'). "
            "Стиль: дружелюбный, ясный, с позитивом и советами. "
            "Структура: оцени охват и вовлечённость, дай 2-3 предложения с выводами и 1-2 совета по улучшению. Пиши только текст анализа."
        ).format(topic=topic, reach=reach, engagement=engagement, context=BOOK_CONTEXT[:1000])
    elif mode == "hashtags":
        full_prompt = (
            "Ты SMM-специалист с 10-летним опытом. "
            "Составь список из 10 актуальных хэштегов на русском языке по теме '{topic}' для социальных сетей. "
            "Пиши исключительно на русском языке, любые иностранные слова запрещены. "
            "Хэштеги должны быть релевантны теме, популярны и подходить для Instagram, ВКонтакте и Telegram. "
            "Пример: для 'кофе' — '#кофе #утро #энергия #вкус #напиток #релакс #кофейня #аромат #бодрость #жизнь'. "
            "Пиши только список хэштегов, разделённых пробелами."
        ).format(topic=topic)

    logger.info(f"Отправка запроса к Together AI для {mode}")
    headers = {"Authorization": f"Bearer {TOGETHER_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "meta-llama/Llama-3-8b-chat-hf",
        "messages": [{"role": "user", "content": full_prompt}],
        "max_tokens": 3000,
        "temperature": 0.5
    }
    for attempt in range(3):
        try:
            response = requests.post(TOGETHER_API_URL, headers=headers, json=payload, timeout=15)
            if response.status_code == 200:
                logger.info("Успешный ответ от Together AI")
                raw_text = response.json()["choices"][0]["message"]["content"].strip()
                logger.info(f"Получен текст от Together AI: {raw_text}")
                corrected_text = correct_text(raw_text)
                if re.search(r'[^\u0400-\u04FF\s\d.,!?():;-]', corrected_text):  # Проверка на не-русские символы
                    logger.warning("Обнаружены не-русские символы, заменяю...")
                    replacements = {
                        'aged': 'в возрасте', 'thoughts': 'мысли', 'confidence': 'уверенность', 'find': 'найти',
                        'hearts': 'сердце', 'regular': 'регулярный', 'grooming': 'уход', 'tips': 'советы', 
                        'satisfied': 'довольные', 'clients': 'клиенты', 'about': 'о', 'our': 'наших', 
                        'services': 'услугах', 'how': 'как', 'to': '', 'keep': 'сохранить', 'your': 'ваши', 
                        'hair': 'волосы', 'healthy': 'здоровыми', 'and': 'и', 'strong': 'сильными', 
                        'care': 'ухаживать', 'for': 'за', 'at': 'дома', 'home': 'дома', 'verbessern': 'улучшить',
                        'spends': 'проводит', 'time': 'время', 'with': 'с', 'family': 'семьёй', 'friends': 'друзьями',
                        'build': 'развить', 'semaine': 'неделя', 'week': 'неделя', 'professional': 'профессиональный',
                        'guidance': 'поддержка', 'consultation': 'консультация', 'cope': 'справляться', 
                        'relationship': 'отношения', 'gratitude': 'благодарность', 'motivation': 'мотивация',
                        'productive': 'продуктивный', 'self': 'себя', 'esteem': 'самооценка', 'overwhelmed': 'перегружен',
                        'anxious': 'тревожный', 'depressed': 'подавленный', 'stress': 'стресс', 'achieve': 'достичь',
                        'goals': 'цели', 'benefit': 'польза', 'therapy': 'терапия', 'pдомаterns': 'шаблоны', 
                        'mindfulness': 'осознанность', 'mental': 'психическое', 'health': 'здоровье'
                    }
                    for eng, rus in replacements.items():
                        corrected_text = corrected_text.replace(eng, rus)
                corrected_text = correct_text(corrected_text)  # Двойная проверка для опечаток
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
        "психолог": ["#психология", "#саморазвитие", "#здоровье", "#эмоции", "#мотивация", "#уверенность"],
        "маркетолог": ["#маркетинг", "#продвижение", "#реклама", "#бизнес", "#лидерство", "#коммуникация"],
        "спортклуб": ["#фитнес", "#спорт", "#здоровье", "#тренировки", "#мотивация", "#сила"],
        "маникюра": ["#маникюр", "#красота", "#уход", "#ногти", "#стиль", "#здоровье"],
        "хоккей": ["#хоккей", "#спорт", "#игра", "#команда", "#мотивация", "#сила"],
        "зиму": ["#зима", "#холод", "#снег", "#уют", "#природа", "#отдых"],
        "барбершопа": ["#барбершоп", "#стрижка", "#уход", "#стиль", "#мужчины", "#красота"],
        "кофе": ["#кофе", "#утро", "#энергия", "#вкус", "#напиток", "#релакс"],
        "курения": ["#здоровье", "#вред", "#курение", "#отказ", "#жизнь", "#мотивация"],
        "поезда": ["#поезда", "#путешествия", "#транспорт", "#технологии", "#дорога", "#приключения"],
        "лето": ["#лето", "#жара", "#отдых", "#солнце", "#природа", "#энергия"]
    }
    relevant_tags = []
    for key in thematic_hashtags:
        if key in topic.lower():
            relevant_tags.extend(thematic_hashtags[key])
            break
    if not relevant_tags:
        relevant_tags = ["#соцсети", "#идеи", "#полезно", "#жизнь"]
    
    combined = list(set(base_hashtags + relevant_tags))
    combined.sort(key=lambda x: (len(x), x in topic.lower()), reverse=True)
    corrected_tags = [correct_text(tag[1:]) for tag in combined[:8]]
    final_tags = [f"#{tag}" for tag in corrected_tags] + ["#инстаграм", "#вконтакте", "#телеграм"]
    return " ".join(final_tags)

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

    # Меню кнопок
    keyboard = [
        ["Пост", "Сторис", "Аналитика"],
        ["Стратегия/Контент-план", "Хэштеги"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    # Обработка кнопок
    if message == "пост":
        user_data[user_id] = {"mode": "post", "stage": "topic"}
        await update.message.reply_text("О чём написать пост? (Например, 'кофе')", reply_markup=reply_markup)
        return
    elif message == "сторис":
        user_data[user_id] = {"mode": "story", "stage": "topic"}
        await update.message.reply_text("О чём написать сторис? (Например, 'утро')", reply_markup=reply_markup)
        return
    elif message == "аналитика":
        user_data[user_id] = {"mode": "analytics", "stage": "topic"}
        await update.message.reply_text("Для чего аналитика? (Например, 'посты про кофе')", reply_markup=reply_markup)
        return
    elif message == "стратегия/контент-план":
        user_data[user_id] = {"mode": "strategy", "stage": "client"}
        await update.message.reply_text("Для кого стратегия? (Опиши аудиторию: возраст, профессия, боли)", reply_markup=reply_markup)
        return
    elif message == "хэштеги":
        user_data[user_id] = {"mode": "hashtags", "stage": "topic"}
        await update.message.reply_text("Для какой темы нужны хэштеги?", reply_markup=reply_markup)
        return

    # Обработка стадий
    if user_id in user_data:
        mode = user_data[user_id]["mode"]
        stage = user_data[user_id]["stage"]

        if mode in ["post", "story", "image", "hashtags", "analytics"] and stage == "topic":
            clean_topic = re.sub(r"^(о|про|для|об|на)\s+", "", message).strip()
            user_data[user_id]["topic"] = clean_topic
            if mode == "hashtags":
                response = generate_text(user_id, "hashtags")
                await update.message.reply_text(response, reply_markup=reply_markup)
                del user_data[user_id]
            elif mode == "analytics":
                user_data[user_id]["stage"] = "reach"
                await update.message.reply_text("Какой охват у вашего контента? (Например, 500 просмотров)", reply_markup=reply_markup)
            else:
                ideas = generate_ideas(clean_topic)
                user_data[user_id]["stage"] = "ideas"
                await update.message.reply_text(f"Вот идеи для '{clean_topic}':\n" + "\n".join(ideas) + "\nВыбери номер идеи (1, 2, 3...) или напиши свою!", reply_markup=reply_markup)
        elif mode in ["post", "story", "image"] and stage == "ideas":
            if message.isdigit() and 1 <= int(message) <= 3:
                idea_num = int(message)
                ideas = generate_ideas(user_data[user_id]["topic"])
                selected_idea = ideas[idea_num - 1].split(". ")[1]
                user_data[user_id]["idea"] = selected_idea
            else:
                user_data[user_id]["idea"] = message
            response = generate_text(user_id, mode)
            hashtags = generate_hashtags(user_data[user_id]["topic"])
            await update.message.reply_text(f"{response}\n\n{hashtags}", reply_markup=reply_markup)
            del user_data[user_id]
        elif mode == "strategy" and stage == "client":
            logger.info("Этап client")
            user_data[user_id]["client"] = message
            user_data[user_id]["stage"] = "channels"
            await update.message.reply_text("Какие каналы вы хотите использовать для привлечения? (Соцсети, реклама, содержание)", reply_markup=reply_markup)
        elif mode == "strategy" and stage == "channels":
            logger.info("Этап channels")
            user_data[user_id]["channels"] = message
            user_data[user_id]["stage"] = "result"
            await update.message.reply_text("Какой главный результат вы хотите получить? (Прибыль, клиенты, узнаваемость)", reply_markup=reply_markup)
        elif mode == "strategy" and stage == "result":
            logger.info("Этап result, генерация стратегии")
            user_data[user_id]["result"] = message
            response = generate_text(user_id, "strategy")
            hashtags = generate_hashtags(user_data[user_id]["topic"])
            topic = user_data[user_id]["topic"]
            try:
                pdf_file = create_pdf(response)
                with open(pdf_file, 'rb') as f:
                    await context.bot.send_document(
                        chat_id=update.message.chat_id,
                        document=f,
                        filename=f"Стратегия_{topic}.pdf",
                        caption=f"Вот твоя стратегия в PDF!\n\n{hashtags}",
                        reply_markup=reply_markup
                    )
                os.remove(pdf_file)
                logger.info(f"Стратегия успешно отправлена как PDF для user_id={user_id}")
                await asyncio.sleep(20)
                await context.bot.send_message(
                    chat_id=update.message.chat_id,
                    text="Хотите контент-план по этой стратегии? (Да/Нет)",
                    reply_markup=reply_markup
                )
                user_data[user_id]["stage"] = "content_plan_offer"
            except Exception as e:
                logger.error(f"Ошибка отправки стратегии как PDF: {e}", exc_info=True)
                await update.message.reply_text("Не удалось отправить стратегию как PDF. Попробуй ещё раз!", reply_markup=reply_markup)
        elif mode == "strategy" and stage == "content_plan_offer":
            if "да" in message:
                logger.info("Пользователь хочет контент-план")
                user_data[user_id]["stage"] = "frequency"
                await update.message.reply_text("Как часто хотите выпускать посты и короткие видео? (Например, '2 поста и 3 видео в неделю')", reply_markup=reply_markup)
            else:
                logger.info("Пользователь отказался от контент-плана")
                del user_data[user_id]
                await update.message.reply_text("Выбери новое действие из меню ниже!", reply_markup=reply_markup)
        elif mode == "content_plan" and stage == "frequency":
            logger.info("Этап frequency, генерация контент-плана")
            user_data[user_id]["frequency"] = message
            response = generate_text(user_id, "content_plan")
            hashtags = generate_hashtags(user_data[user_id]["topic"])
            topic = user_data[user_id]["topic"]
            try:
                pdf_file = create_pdf(response)
                with open(pdf_file, 'rb') as f:
                    await context.bot.send_document(
                        chat_id=update.message.chat_id,
                        document=f,
                        filename=f"Контент-план_{topic}.pdf",
                        caption=f"Вот твой контент-план в PDF!\n\n{hashtags}",
                        reply_markup=reply_markup
                    )
                os.remove(pdf_file)
                logger.info(f"Контент-план успешно отправлен как PDF для user_id={user_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки контент-плана как PDF: {e}", exc_info=True)
                await update.message.reply_text("Не удалось отправить контент-план как PDF. Попробуй ещё раз!", reply_markup=reply_markup)
            del user_data[user_id]
        elif mode == "analytics" and stage == "reach":
            logger.info("Этап reach")
            user_data[user_id]["reach"] = message
            user_data[user_id]["stage"] = "engagement"
            await update.message.reply_text("Какая вовлечённость у вашего контента? (Например, 50 лайков, 10 комментариев)", reply_markup=reply_markup)
        elif mode == "analytics" and stage == "engagement":
            logger.info("Этап engagement, генерация аналитики")
            user_data[user_id]["engagement"] = message
            response = generate_text(user_id, "analytics")
            hashtags = generate_hashtags(user_data[user_id]["topic"])
            await update.message.reply_text(f"{response}\n\n{hashtags}", reply_markup=reply_markup)
            del user_data[user_id]
    else:
        await update.message.reply_text("Выбери действие из меню ниже!", reply_markup=reply_markup)

# Обработка текстовых сообщений
async def handle_text(update: Update, context: ContextTypes):
    logger.info(f"Обработка текстового сообщения от {update.message.from_user.id}: {update.message.text}")
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
    logger.info(f"Получена команда /start от user_id={update.message.from_user.id}")
    keyboard = [
        ["Пост", "Сторис", "Аналитика"],
        ["Стратегия/Контент-план", "Хэштеги"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "Привет! Я твой SMM-помощник. Выбери, что я сделаю для тебя:",
        reply_markup=reply_markup
    )

# Webhook handler
async def webhook(request):
    logger.info("Получен запрос на webhook")
    try:
        update = Update.de_json(await request.json(), app.bot)
        if update:
            logger.info(f"Получен update: {update}")
            await app.process_update(update)
        else:
            logger.warning("Update пустой")
        return web.Response(text="OK")
    except Exception as e:
        logger.error(f"Ошибка в webhook: {e}", exc_info=True)
        return web.Response(text="ERROR", status=500)

# Настройка и запуск
async def init_app():
    logger.info("Инициализация бота...")
    await app.initialize()
    hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "localhost")
    webhook_url = f"https://{hostname}/webhook"
    try:
        current_webhook = await app.bot.get_webhook_info()
        logger.info(f"Текущий вебхук: {current_webhook}")
        if current_webhook.url != webhook_url:
            await app.bot.set_webhook(url=webhook_url)
            logger.info(f"Webhook установлен: {webhook_url}")
        else:
            logger.info("Webhook уже установлен корректно")
    except Exception as e:
        logger.error(f"Ошибка при настройке вебхука: {e}", exc_info=True)
        raise

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
    logger.info(f"Слушаю порт {PORT}")
    web.run_app(main(), host="0.0.0.0", port=PORT)