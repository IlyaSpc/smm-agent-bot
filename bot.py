import os
import logging
from typing import Dict, List, Optional, Any
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import aiohttp
import re
import asyncio
from aiohttp import web
import json

# Логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
class Config:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
    TOGETHER_API_URL = "https://api.together.xyz/v1/chat/completions"
    PROMPTS_URL = "https://drive.usercontent.google.com/download?id=1byy2KMAGV3Thg0MwH94PMQEjoA3BwqWK&export=download"
    PORT = int(os.getenv("PORT", 10000))

    @classmethod
    def validate(cls):
        required = {"TELEGRAM_BOT_TOKEN": cls.TELEGRAM_BOT_TOKEN, "TOGETHER_API_KEY": cls.TOGETHER_API_KEY}
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ValueError(f"Missing environment variables: {', '.join(missing)}")

Config.validate()
app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).read_timeout(30).write_timeout(30).build()

# Константы
BASE_KEYBOARD = ReplyKeyboardMarkup([
    ["Пост", "Сторис", "Reels"],
    ["Аналитика", "Конкуренты", "А/Б тест"],
    ["Стратегия/Контент-план", "Хэштеги"]
], resize_keyboard=True)

STYLE_KEYBOARD = ReplyKeyboardMarkup([["Формальный", "Дружелюбный", "Саркастичный"]], resize_keyboard=True)
TONE_KEYBOARD = ReplyKeyboardMarkup([["Миллениалы", "Бизнес-аудитория", "Gen Z"]], resize_keyboard=True)
TEMPLATE_KEYBOARD = ReplyKeyboardMarkup([["Стандарт", "Объявление"], ["Опрос", "Кейс"]], resize_keyboard=True)

# Кэш промтов и обработанных обновлений
PROMPTS: Dict[str, str] = {}
PROCESSED_UPDATES: set = set()

async def load_prompts() -> None:
    async with aiohttp.ClientSession() as session:
        async with جلسه.get(Config.PROMPTS_URL) as response:
            if response.status == 200:
                raw_data = await response.read()
                logger.info(f"Сырой ответ от Google Drive: {raw_data[:100]}...")
                try:
                    PROMPTS.update(json.loads(raw_data.decode('utf-8')))
                    logger.info("Промты успешно загружены")
                except json.JSONDecodeError as e:
                    logger.error(f"Ошибка декодирования JSON: {e}")
                    raise ValueError("Не удалось разобрать prompts.json из Google Drive")
            else:
                logger.error(f"Ошибка загрузки промтов: {response.status} - {await response.text()}")
                raise ValueError(f"Не удалось загрузить prompts.json: {response.status}")

async def get_prompt(prompt_name: str) -> str:
    return PROMPTS.get(prompt_name, f"Ошибка: промт '{prompt_name}' не найден")

async def call_together_api(prompt: str, max_tokens: int = 500) -> str:
    headers = {"Authorization": f"Bearer {Config.TOGETHER_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "meta-llama/Llama-3-8b-chat-hf",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.5
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(Config.TOGETHER_API_URL, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    data = await response.json()
                    raw_text = data["choices"][0]["message"]["content"].strip()
                    logger.info(f"Сырой ответ API: {raw_text[:100]}...")
                    return raw_text
                logger.error(f"Ошибка API Together: {response.status} - {await response.text()}")
                return "Ошибка API"
    except Exception as e:
        logger.error(f"Ошибка вызова Together API: {e}")
        return "Сервер не отвечает 😓"

async def generate_content(user_id: int, mode: str, topic: str, style: str = "дружелюбный") -> str:
    user_data = app.bot_data.setdefault(user_id, {})
    niche = user_data.get("niche", "не_указано")
    prompt_template = await get_prompt(mode)
    if "ошибка" in prompt_template.lower():
        return prompt_template

    try:
        # Ниша как направление мышления, а не часть текста
        context = f"Ты работаешь в нише '{niche}' — это область деятельности, которая задаёт направление твоего мышления (например, автоматизация, чат-боты, воронки продаж). Сфокусируйся на теме '{topic}' и не упоминай нишу в тексте напрямую. Пиши только на русском языке, без английских слов."
        if mode in {"post", "strategy", "competitor_analysis", "ab_testing", "hashtags"}:
            full_prompt = context + "\n" + prompt_template.format(
                topic=topic.replace('_', ' '),
                style=style,
                tone=user_data.get("tone", "универсальный"),
                template=user_data.get("template", "стандарт"),
                client=user_data.get("client", "не_указано"),
                channels=user_data.get("channels", "не_указано"),
                result=user_data.get("result", "не_указано"),
                competitor_keyword=user_data.get("competitor_keyword", "не_указано")
            )
            return await call_together_api(full_prompt, 2000 if mode == "strategy" else 500)
        elif mode in {"ideas", "reels", "stories"}:
            full_prompt = context + "\n" + prompt_template.format(topic=topic.replace('_', ' '), style=style)
            raw_text = await call_together_api(full_prompt)
            ideas = [line.strip() for line in raw_text.split("\n") if line.strip() and not line.startswith("#")]
            ideas = [re.sub(r'^\d+\.\s*|\*\*.*\*\*\s*', '', idea) for idea in ideas if len(idea.split()) > 5][:3]
            if not ideas:
                ideas = ["Искры гениальности кончились — попробуй ещё раз!"]
            return "\n".join(f"{i+1}. {idea}" for i, idea in enumerate(ideas))
    except KeyError as e:
        logger.error(f"Ошибка форматирования промта: {e}")
        return f"Ошибка: отсутствует параметр {e}"
    return "Неизвестная ошибка"

# Машина состояний
STATES: Dict[str, Dict[str, Any]] = {
    "start": {"text": "Привет! Как тебя зовут?", "next": "name"},
    "name": {"text": "В какой нише работаешь?", "next": "niche"},
    "niche": {"text": "Что делаем?", "next": "main", "keyboard": BASE_KEYBOARD},
    "main": {"text": "Выбери действие!", "keyboard": BASE_KEYBOARD},
    "post_topic": {"text": "О чём написать пост?", "next": "post_style"},
    "post_style": {"text": "Какой стиль текста?", "next": "post_tone", "keyboard": STYLE_KEYBOARD},
    "post_tone": {"text": "Выбери тон для аудитории:", "next": "post_template", "keyboard": TONE_KEYBOARD},
    "post_template": {"text": "Выбери шаблон:", "next": "post_ideas", "keyboard": TEMPLATE_KEYBOARD},
    "post_ideas": {"text": lambda uid: f"Вот идеи:\n{app.bot_data[uid]['ideas']}\nВыбери номер (1, 2, 3)!", "next": "post_generate"},
    "post_generate": {"text": lambda uid: f"Вот твой пост:\n{app.bot_data[uid]['post']}", "next": "main", "keyboard": BASE_KEYBOARD},
    "stories_topic": {"text": "О чём снять сторис?", "next": "stories_generate"},
    "stories_generate": {"text": lambda uid: f"Вот идеи для сторис:\n{app.bot_data[uid]['ideas']}", "next": "main", "keyboard": BASE_KEYBOARD},
    "reels_topic": {"text": "О чём снять Reels?", "next": "reels_generate"},
    "reels_generate": {"text": lambda uid: f"Вот идеи для Reels:\n{app.bot_data[uid]['ideas']}", "next": "main", "keyboard": BASE_KEYBOARD},
    "competitors_keyword": {"text": "Укажи ключевое слово конкурентов!", "next": "competitors_generate"},
    "competitors_generate": {"text": lambda uid: f"Анализ конкурентов:\n{app.bot_data[uid]['analysis']}", "next": "main", "keyboard": BASE_KEYBOARD},
    "ab_test_topic": {"text": "Для чего тестируем заголовки?", "next": "ab_test_generate"},
    "ab_test_generate": {"text": lambda uid: f"Вот 3 заголовка:\n{app.bot_data[uid]['headlines']}\nВыбери номер (1, 2, 3)!", "next": "main", "keyboard": BASE_KEYBOARD},
    "strategy_topic": {"text": "По какой теме стратегия?", "next": "strategy_client"},
    "strategy_client": {"text": "Кто целевая аудитория?", "next": "strategy_channels"},
    "strategy_channels": {"text": "Какие каналы продвижения?", "next": "strategy_result"},
    "strategy_result": {"text": "Какой результат нужен?", "next": "strategy_generate"},
    "strategy_generate": {"text": lambda uid: f"Вот стратегия:\n{app.bot_data[uid]['strategy']}", "next": "main", "keyboard": BASE_KEYBOARD},
    "hashtags_topic": {"text": "По какой теме хэштеги?", "next": "hashtags_generate"},
    "hashtags_generate": {"text": lambda uid: f"Вот хэштеги:\n{app.bot_data[uid]['hashtags']}", "next": "main", "keyboard": BASE_KEYBOARD},
    "analytics": {"text": "Функция 'Аналитика' пока в разработке. Скоро будет!", "next": "main", "keyboard": BASE_KEYBOARD},
}

async def handle_message(update: Update, context: ContextTypes) -> None:
    user_id = update.message.from_user.id
    message = update.message.text.lower().strip()
    logger.info(f"Получено сообщение от {user_id}: {message}")

    user_data = app.bot_data.setdefault(user_id, {"state": "start"})
    state = user_data["state"]

    if message == "/start":
        user_data.clear()
        user_data["state"] = "start"
        state_info = STATES["start"]
        await update.message.reply_text(state_info["text"])
        user_data["state"] = state_info["next"]
        return

    state_info = STATES.get(state, {"text": "Выбери действие!", "keyboard": BASE_KEYBOARD})

    if state in {"name", "niche"}:
        user_data[state] = message.capitalize() if state == "name" else message
    elif state.startswith("post_"):
        if state == "post_ideas" and message.isdigit() and 1 <= int(message) <= 3:
            user_data["post"] = await generate_content(user_id, "post", user_data["topic"], user_data["style"])
        elif state == "post_generate":
            pass
        else:
            user_data[state.split("_")[1]] = message.lower() if state == "post_tone" else message
            if state == "post_template":
                user_data["ideas"] = await generate_content(user_id, "ideas", user_data["topic"], user_data["style"])
    elif state in {"stories_topic", "reels_topic"}:
        user_data["topic"] = message.replace(" ", "_")
        user_data["ideas"] = await generate_content(user_id, "stories" if state == "stories_topic" else "reels", user_data["topic"])
    elif state == "competitors_keyword":
        user_data["competitor_keyword"] = message
        user_data["analysis"] = await generate_content(user_id, "competitor_analysis", message)
    elif state == "ab_test_topic":
        user_data["topic"] = message.replace(" ", "_")
        user_data["headlines"] = await generate_content(user_id, "ab_testing", user_data["topic"])
    elif state.startswith("strategy_"):
        user_data[state.split("_")[1]] = message
        if state == "strategy_result":
            user_data["strategy"] = await generate_content(user_id, "strategy", user_data["topic"])
    elif state == "hashtags_topic":
        user_data["topic"] = message.replace(" ", "_")
        user_data["hashtags"] = await generate_content(user_id, "hashtags", user_data["topic"])
    elif state == "main":
        next_state = {
            "пост": "post_topic",
            "сторис": "stories_topic",
            "reels": "reels_topic",
            "аналитика": "analytics",
            "конкуренты": "competitors_keyword",
            "а/б тест": "ab_test_topic",
            "стратегия/контент-план": "strategy_topic",
            "хэштеги": "hashtags_topic"
        }.get(message)
        if next_state:
            user_data["state"] = next_state
            state_info = STATES[next_state]
            await update.message.reply_text(state_info["text"], reply_markup=state_info.get("keyboard"))
            return

    next_state = state_info.get("next", "main")
    user_data["state"] = next_state
    next_info = STATES.get(next_state, {"text": "Выбери действие!", "keyboard": BASE_KEYBOARD})
    
    if callable(next_info["text"]):
        text = next_info["text"](user_id)
    else:
        text = next_info["text"]
        if next_state == "niche":
            text = f"Отлично, {user_data.get('name', 'друг')}! В какой нише работаешь?"
        elif next_state == "main":
            text = f"Круто, ниша '{user_data.get('niche', 'не указана')}'! Что делаем?"

    await update.message.reply_text(text, reply_markup=next_info.get("keyboard"))

# Webhook
async def webhook(request: web.Request) -> web.Response:
    try:
        logger.info("Получен запрос на /webhook")
        data = await request.json()
        update_id = data.get("update_id")
        if update_id in PROCESSED_UPDATES:
            logger.warning(f"Дубликат update_id: {update_id}")
            return web.Response(text="Duplicate", status=200)
        PROCESSED_UPDATES.add(update_id)
        update = Update.de_json(data, app.bot)
        if update:
            await app.process_update(update)
            return web.Response(text="OK", status=200)
        return web.Response(text="No update", status=400)
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка декодирования JSON: {e}")
        return web.Response(text="Invalid JSON", status=400)
    except Exception as e:
        logger.error(f"Ошибка в webhook: {e}", exc_info=True)
        return web.Response(text="Error", status=500)

async def health_check(request: web.Request) -> web.Response:
    return web.Response(text="OK", status=200)

async def main() -> None:
    await app.initialize()
    await app.start()
    await load_prompts()

    web_app = web.Application()
    web_app.router.add_post('/webhook', webhook)
    web_app.router.add_get('/health', health_check)

    app.add_handler(CommandHandler("start", handle_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', Config.PORT)
    await site.start()
    logger.info(f"Сервер запущен на порту {Config.PORT}")

    try:
        await asyncio.Event().wait()
    finally:
        await app.stop()
        await runner.cleanup()

if __name__ == "__main__":
    logger.info("Запуск бота...")
    asyncio.run(main())