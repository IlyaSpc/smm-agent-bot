import os
import json
import requests
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, ConversationHandler, filters
import logging
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm
from io import BytesIO

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler (для постов)
THEME, STYLE, TEMPLATE, IDEAS, EDIT = range(5)

# Состояния для ConversationHandler (для стратегии)
GOAL, AUDIENCE, PERIOD = range(3)

# Хранилище подписок и дат окончания
subscriptions = {}
subscription_expiry = {}
trial_start = {}

# ID разработчика
DEVELOPER_ID = 477468896

# Загрузка промптов из JSON
try:
    with open('prompts.json', 'r', encoding='utf-8') as f:
        PROMPTS = json.load(f)
except FileNotFoundError:
    logger.error("Файл prompts.json не найден")
    PROMPTS = {}

# Настройка Together AI
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
TOGETHER_API_URL = "https://api.together.xyz/v1/chat/completions"

# Функция для генерации текста через Together AI (LLaMA-3-8B)
def generate_with_together(prompt):
    headers = {
        "Authorization": f"Bearer {TOGETHER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "meta-llama/Llama-3-8b-chat-hf",
        "messages": [
            {"role": "system", "content": "Ты копирайтер с 10-летним опытом, работающий на русском языке."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 1000,
        "temperature": 0.7,
        "top_p": 0.9
    }
    try:
        response = requests.post(TOGETHER_API_URL, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            result = response.json()
            return result["choices"][0]["message"]["content"].strip()
        else:
            logger.error(f"Ошибка Together AI: {response.status_code} - {response.text}")
            return "Не удалось сгенерировать текст. Попробуй позже! 😔"
    except Exception as e:
        logger.error(f"Ошибка при вызове Together AI: {e}")
        return "Не удалось сгенерировать текст. Попробуй позже! 😔"

# Функция для генерации хэштегов
def generate_hashtags(topic):
    words = topic.split()
    base_hashtags = [f"#{word}" for word in words if len(word) > 2]
    thematic_hashtags = {
        "мода": ["#мода", "#стиль", "#тренды", "#образ", "#вдохновение"],
        "кофе": ["#кофе", "#утро", "#энергия", "#вкус", "#напиток"],
        "фитнес": ["#фитнес", "#спорт", "#здоровье", "#мотивация", "#тренировки"]
    }
    relevant_tags = []
    topic_lower = topic.lower()
    for key in thematic_hashtags:
        if key in topic_lower:
            relevant_tags.extend(thematic_hashtags[key])
            break
    if not relevant_tags:
        relevant_tags = ["#соцсети", "#жизнь", "#идеи", "#полезно", "#вдохновение"]
    combined = list(dict.fromkeys(base_hashtags + relevant_tags))[:10]
    return " ".join(combined)

# Функция для проверки подписки
def check_subscription(user_id):
    if user_id == DEVELOPER_ID:
        subscriptions[user_id] = "lifetime"
        subscription_expiry[user_id] = None
        return True
    if user_id not in subscriptions or subscriptions[user_id] == "none":
        if user_id not in trial_start:
            trial_start[user_id] = datetime.now()
            subscriptions[user_id] = "full"
            subscription_expiry[user_id] = trial_start[user_id] + timedelta(days=3)
            return True
        else:
            if datetime.now() > subscription_expiry[user_id]:
                subscriptions[user_id] = "none"
                return False
            return True
    if subscriptions[user_id] in ["lite", "full"]:
        if datetime.now() > subscription_expiry[user_id]:
            subscriptions[user_id] = "none"
            return False
    return True

# Функция для генерации PDF
def generate_pdf(strategy_text):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    
    pdfmetrics.registerFont(TTFont('DejaVuSans', 'DejaVuSans.ttf'))
    c.setFont('DejaVuSans', 12)

    width, height = A4
    margin = 20 * mm
    y_position = height - margin

    c.setFont('DejaVuSans', 16)
    c.drawString(margin, y_position, "SMM-стратегия и контент-план")
    y_position -= 20 * mm

    c.setFont('DejaVuSans', 12)
    lines = strategy_text.split('\n')
    for line in lines:
        if y_position < margin:
            c.showPage()
            c.setFont('DejaVuSans', 12)
            y_position = height - margin
        c.drawString(margin, y_position, line)
        y_position -= 5 * mm

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    check_subscription(user_id)

    welcome_message = (
        "Привет! Я SMM Agent Bot — твой помощник в создании контента. 🎉\n"
        "У тебя 3 дня бесплатного доступа к Полной версии! Попробуй сгенерировать пост ('Пост'), "
        "идеи для Reels ('Reels') или стратегию ('/стратегия').\n\n"
        "Меня создал Илья Чечуев (@i_chechuev). Подписывайся на мой Telegram-канал @ChechuevSMM, "
        "чтобы узнать больше о SMM и ботах!\n\n"
        "Если пробный период закончится, оформи подписку: /подписка\n\n"
        "Что делаем?"
    )
    await update.message.reply_text(welcome_message)

# Команда /подписка
async def podpiska(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_subscription(user_id):
        message = (
            "Выбери вариант:\n"
            "1. Лайт — 300 руб./мес (или 1620 руб. за 6 мес, 2880 руб. за год)\n"
            "2. Полная — 600 руб./мес (или 3240 руб. за 6 мес, 5760 руб. за год)\n"
            "3. Разовая покупка — 10 000 руб. (навсегда)\n\n"
            "Платежи временно недоступны. Напиши @i_chechuev для оплаты вручную."
        )
        await update.message.reply_text(message)
    else:
        expiry_date = subscription_expiry[user_id].strftime("%Y-%m-%d") if subscription_expiry[user_id] else "навсегда"
        await update.message.reply_text(
            f"У тебя уже есть подписка: {subscriptions[user_id]} (до {expiry_date}).\n"
            "Хочешь продлить или изменить подписку? Напиши /подписка."
        )

# Команда /стратегия
async def strategiya(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_subscription(user_id):
        await update.message.reply_text(
            "Твой пробный период истёк! Оформи подписку: /подписка"
        )
        return ConversationHandler.END

    if subscriptions[user_id] not in ["full", "lifetime"]:
        await update.message.reply_text(
            "Функция 'Стратегия' доступна только в Полной версии. Оформи подписку: /подписка"
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "Какая у тебя цель? Например: Увеличить вовлечённость, Привлечь подписчиков, Продать продукт."
    )
    return GOAL

# Обработчик для ConversationHandler (стратегия)
async def goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['goal'] = update.message.text
    await update.message.reply_text(
        "Кто твоя целевая аудитория? Например: Молодёжь 18-25 лет, интересуются модой, активны в Instagram."
    )
    return AUDIENCE

async def audience(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['audience'] = update.message.text
    await update.message.reply_text(
        "На какой период нужен план? Например: 1 неделя, 1 месяц."
    )
    return PERIOD

async def period(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['period'] = update.message.text
    goal = context.user_data['goal']
    audience = context.user_data['audience']
    period = context.user_data['period']

    # Определяем тип стратегии на основе цели
    goal_lower = goal.lower()
    if "вовлечённость" in goal_lower:
        strategy_type = "engagement"
    elif "подписчиков" in goal_lower:
        strategy_type = "followers"
    elif "продать" in goal_lower or "продаж" in goal_lower:
        strategy_type = "sales"
    else:
        strategy_type = "engagement"

    # Загружаем промпт из JSON
    strategy_prompt = PROMPTS.get("strategy", {}).get(strategy_type, "Составь SMM-стратегию. Аудитория: {audience}, период: {period}.")
    strategy_prompt = strategy_prompt.format(audience=audience, channels="Instagram, Telegram", result="увеличение вовлечённости")

    # Генерируем стратегию через Together AI
    strategy_text = generate_with_together(strategy_prompt)

    # Генерируем хэштеги
    hashtags = generate_hashtags("мода")

    # Генерируем PDF
    pdf_buffer = generate_pdf(strategy_text)

    # Отправляем PDF пользователю
    await update.message.reply_document(
        document=pdf_buffer,
        filename=f"SMM_Strategy_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
        caption=f"Вот твоя SMM-стратегия и контент-план! 📄\n\n{hashtags}"
    )

    return ConversationHandler.END

# Обработчик текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_subscription(user_id):
        await update.message.reply_text(
            "Твой пробный период истёк! Оформи подписку: /подписка"
        )
        return

    text = update.message.text
    subscription_type = subscriptions.get(user_id, "lite")

    if text == "Пост":
        if subscription_type in ["lite", "full"]:
            await update.message.reply_text("О чём написать пост? (укажи тему)")
            return THEME
        else:
            await update.message.reply_text("Эта функция доступна только с подпиской. Оформи: /подписка")
    else:
        await update.message.reply_text("Я понимаю команды 'Пост' и '/стратегия'. Скоро добавлю больше функций! 😊")

# Обработчик для ConversationHandler (посты)
async def theme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    context.user_data['theme'] = update.message.text

    if subscriptions[user_id] == "full":
        await update.message.reply_text("Какой стиль текста? Формальный, Дружелюбный, Саркастичный")
        return STYLE
    else:
        await update.message.reply_text("Выбери шаблон: Стандарт, Объявление, Опрос, Кейс")
        return TEMPLATE

async def style(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['style'] = update.message.text
    await update.message.reply_text("Выбери шаблон: Стандарт, Объявление, Опрос, Кейс")
    return TEMPLATE

async def template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['template'] = update.message.text
    theme = context.user_data['theme']
    style = context.user_data.get('style', 'Дружелюбный').lower()
    template = context.user_data['template']

    # Генерация идей (пока заглушка, можно добавить позже)
    ideas = [
        f"Идея 1: Показать пользу {theme} в стиле {style}",
        f"Идея 2: Рассказать историю про {theme} в стиле {style}",
        f"Идея 3: Создать опрос про {theme} в стиле {style}"
    ]
    context.user_data['ideas'] = ideas
    await update.message.reply_text("Вот несколько идей:\n" + "\n".join(ideas) + "\n\nВыбери идею (1, 2, 3)")
    return IDEAS

async def ideas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idea_number = update.message.text
    theme = context.user_data['theme']
    style = context.user_data.get('style', 'Дружелюбный').lower()
    template = context.user_data['template']
    ideas = context.user_data['ideas']

    if idea_number in ["1", "2", "3"]:
        idea = ideas[int(idea_number) - 1].split(": ")[1]
    else:
        idea = "Показать пользу темы"

    # Загружаем промпт из JSON
    post_prompt = PROMPTS.get("post", {}).get(style, "Создай пост на тему {theme} в формате {template}.")
    post_prompt = post_prompt.format(
        theme=theme,
        template=template,
        idea=idea,
        goal="привлечение",
        main_idea="показать пользу темы",
        facts="основаны на реальных примерах",
        pains="нехватка времени и информации"
    )

    # Генерируем пост через Together AI
    post = generate_with_together(post_prompt)

    # Генерируем хэштеги
    hashtags = generate_hashtags(theme)

    # Сохраняем результат для редактирования
    context.user_data['last_result'] = post

    await update.message.reply_text(f"Готовый пост:\n{post}\n\n{hashtags}\n\nЕсли хочешь отредактировать, напиши 'Отредактировать'")
    return EDIT

async def edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text.lower() == "отредактировать":
        await update.message.reply_text("Что исправить в посте? (например, 'убери слово кофе')")
        return EDIT
    elif text.lower() == "отмена":
        await update.message.reply_text("Отменено. Напиши 'Пост' или '/стратегия', чтобы начать заново.")
        return ConversationHandler.END
    else:
        edit_request = text
        last_result = context.user_data['last_result']
        style = context.user_data.get('style', 'Дружелюбный').lower()
        template = context.user_data['template']

        # Формируем промпт для редактирования
        edit_prompt = (
            f"Перепиши текст на русском языке: '{last_result}' с учётом запроса пользователя: '{edit_request}'. "
            f"Сохрани стиль: {style}, шаблон: {template}. Пиши ТОЛЬКО НА РУССКОМ ЯЗЫКЕ, без иностранных слов. "
            f"Верни только исправленный текст."
        )

        # Редактируем через Together AI
        edited_post = generate_with_together(edit_prompt)

        # Обновляем результат
        context.user_data['last_result'] = edited_post

        await update.message.reply_text(f"Исправленный пост:\n{edited_post}\n\nЕсли нужно ещё что-то изменить, напиши 'Отредактировать', или 'Отмена' для завершения.")
        return EDIT

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено. Напиши 'Пост' или '/стратегия', чтобы начать заново.")
    return ConversationHandler.END

# Основная функция
def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN не установлен")
        return

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("подписка", podpiska))

    strategy_handler = ConversationHandler(
        entry_points=[CommandHandler("стратегия", strategiya)],
        states={
            GOAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, goal)],
            AUDIENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, audience)],
            PERIOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, period)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(strategy_handler)

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
        states={
            THEME: [MessageHandler(filters.TEXT & ~filters.COMMAND, theme)],
            STYLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, style)],
            TEMPLATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, template)],
            IDEAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, ideas)],
            EDIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(conv_handler)

    logger.info("Бот запущен")
    application.run_polling()

if __name__ == '__main__':
    main()