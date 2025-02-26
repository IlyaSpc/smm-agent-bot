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
from fpdf import FPDF
import asyncio

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
PORT = int(os.environ.get("PORT", 8080))

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

# Генерация идей для постов, сторис и т.д.
def generate_ideas(topic):
    return [
        f"1. Расскажи, как {topic} помогает решать повседневные проблемы.",
        f"2. Поделись фактом о {topic}, который удивит твоих подписчиков.",
        f"3. Покажи, как {topic} меняет жизнь к лучшему на примере."
    ]

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
                "Пиши исключительно на русском языке, любые иностранные слова категорически запрещены — используй только русские эквиваленты (например, 'firsthand' — 'из первых рук', 'like' — 'например'). "
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
            "4) Опиши момент покупки: эмоции (например, отчаяние, надежда), желания (например, найти решение), барьеры (например, страх потратить деньги впустую, недоверие к психологам), добавь больше деталей и эмоций, связанных с услугами психолога, исключи упоминания стрижек или других нерелевантных услуг. "
            "5) Создай 5 реалистичных пользовательских персонажей, представляющих ЦА. Для каждого укажи: "
            "   - Имя "
            "   - Демография (возраст, пол, род занятий, местоположение) "
            "   - Основные цели и мотивации "
            "   - Основные проблемы и боли "
            "   - Повседневные занятия "
            "   - Цитата персоны. "
            "Персонажи должны быть разными, реалистичными, основанными на ЦА и теме. "
            "6) После каждого персонажа добавь подзаголовок 'Как делать!' и предложи уникальный план действий, как мне, как SMM-специалисту, превратить эту персону в клиента бизнеса. Какие способы взаимодействия я могу использовать? Как продавать через соцсети? Распиши по шагам (3-5 шагов) действия, чтобы продать сегменту этой персоны услуги психолога, учитывая её профессию и боли. Планы должны быть уникальными для каждой персоны, используй разные форматы (посты, короткие видео, сторис, вебинары, карусели, прямые эфиры) и соцсети (Instagram, ВКонтакте, Telegram), избегая повторений. "
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
            "Пример текста: '27 февраля 2025, 10:00 - пост: Как справляться со стрессом? Советы психолога помогут вам!' "
            "Составь план на 2 недели, укажи: "
            "1) Дату и время публикации для каждого поста или видео, начиная с 27 февраля 2025 года. "
            "2) Тип контента (пост, короткое видео). "
            "3) Краткое описание (2-3 предложения) с идеей контента, связанной с темой '{topic}'. "
            "4) Цель (привлечение, прогрев, продажа). "
            "Если частота публикаций — '2 поста и 3 видео в неделю', создай ровно 4 поста и 6 коротких видео за 2 недели, распредели контент равномерно, используй только посты и короткие видео. Пиши только текст контент-плана."
        ).format(topic=topic, client=client, channels=channels, frequency=frequency, context=BOOK_CONTEXT[:1000])

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
        "барбершопа": ["#барбершоп", "#стрижка", "#уход", "#стиль", "#мужчины", "#красота"]
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

    # Проверяем, новый ли это запрос
    new_request = any(x in message for x in ["пост про", "напиши пост про", "пост для", "напиши текст про",
                                            "стори про", "напиши стори", "сторителлинг", "сторис", "стори для",
                                            "стратегия про", "напиши стратегию", "стратегия для",
                                            "изображение про", "изображение для",
                                            "аналитика", "анализируй"])
    
    if new_request or user_id not in user_data:
        logger.info("Новый запрос, проверяем тип")
        if user_id in user_data:
            del user_data[user_id]  # Очищаем старые данные для нового запроса
        
        recognized = False
        topic = None
        if any(x in message for x in ["пост про", "напиши пост про", "пост для", "напиши текст про"]):
            user_data[user_id] = {"mode": "post", "stage": "ideas"}
            topic = re.sub(r"(пост про|напиши пост про|пост для|напиши текст про)", "", message).strip()
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
        if user_data[user_id]["mode"] in ["post", "story", "image"] and user_data[user_id]["stage"] == "ideas":
            if message.isdigit() and 1 <= int(message) <= 3:
                idea_num = int(message)
                ideas = generate_ideas(user_data[user_id]["topic"])
                selected_idea = ideas[idea_num - 1].split(". ")[1]
                user_data[user_id]["idea"] = selected_idea
            else:
                user_data[user_id]["idea"] = message
            response = generate_text(user_id, user_data[user_id]["mode"])
            hashtags = generate_hashtags(user_data[user_id]["topic"])
            await update.message.reply_text(f"{response}\n\n{hashtags}")
            del user_data[user_id]
        elif user_data[user_id]["mode"] == "strategy" or user_data[user_id]["mode"] == "content_plan":
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
                topic = user_data[user_id]["topic"]
                try:
                    pdf_file = create_pdf(response)
                    with open(pdf_file, 'rb') as f:
                        await context.bot.send_document(
                            chat_id=update.message.chat_id,
                            document=f,
                            filename=f"Стратегия_{topic}.pdf",
                            caption=f"Вот твоя стратегия в PDF!\n\n{hashtags}"
                        )
                    os.remove(pdf_file)
                    logger.info(f"Стратегия успешно отправлена как PDF для user_id={user_id}")
                    await asyncio.sleep(20)
                    await context.bot.send_message(
                        chat_id=update.message.chat_id,
                        text="Хотите контент-план по этой стратегии? (Да/Нет)"
                    )
                    user_data[user_id]["stage"] = "content_plan_offer"
                except Exception as e:
                    logger.error(f"Ошибка отправки стратегии как PDF: {e}", exc_info=True)
                    await update.message.reply_text("Не удалось отправить стратегию как PDF. Попробуй ещё раз!")
            elif user_data[user_id]["stage"] == "content_plan_offer":
                if "да" in message:
                    logger.info("Пользователь хочет контент-план")
                    user_data[user_id]["stage"] = "frequency"
                    await update.message.reply_text("Как часто хотите выпускать посты и короткие видео? (Например, '2 поста и 3 видео в неделю')")
                else:
                    logger.info("Пользователь отказался от контент-плана")
                    del user_data[user_id]
            elif user_data[user_id]["stage"] == "frequency":
                logger.info("Этап frequency, генерация контент-плана")
                user_data[user_id]["frequency"] = message
                user_data[user_id]["mode"] = "content_plan"
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
                            caption=f"Вот твой контент-план в PDF!\n\n{hashtags}"
                        )
                    os.remove(pdf_file)
                    logger.info(f"Контент-план успешно отправлен как PDF для user_id={user_id}")
                except Exception as e:
                    logger.error(f"Ошибка отправки контент-плана как PDF: {e}", exc_info=True)
                    await update.message.reply_text("Не удалось отправить контент-план как PDF. Попробуй ещё раз!")
                del user_data[user_id]

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
    await update.message.reply_text(
        "Привет! Я твой SMM-помощник. Могу писать посты, сторис, стратегии и контент-планы для Instagram, ВКонтакте и Telegram.\n"
        "Примеры запросов: 'пост про кофе', 'стори для города', 'стратегия для маркетолога'.\n"
        "Отвечай на мои вопросы, чтобы получить сильный текст или стратегию!\n"
        "Задержка ответа — от 5 до 20 секунд, пока я думаю над твоим запросом. Если я долго не отвечаю, подожди чуть-чуть — возможно, я просыпаюсь! 😊"
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