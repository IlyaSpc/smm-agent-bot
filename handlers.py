from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from utils import check_subscription, generate_with_together, generate_hashtags, generate_pdf, PROMPTS, subscriptions
from datetime import datetime
import logging
import os

logger = logging.getLogger(__name__)

THEME, STYLE, TEMPLATE, IDEAS, EDIT = range(5)
GOAL, AUDIENCE, PERIOD = range(3)

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [["Пост", "Рилс"], ["Стратегия", "Хештеги"], ["А/Б тест"]],
    resize_keyboard=True
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Команда /start получена от пользователя {update.effective_user.id}")
    user_id = update.effective_user.id
    check_subscription(user_id)

    welcome_message = (
        "Привет! Я SMM-помощник в создании контента. 🎉\n"
        "У тебя 3 дня бесплатного доступа к Полной версии! Попробуй сгенерировать пост, идеи для Reels или стратегию и контент план."
    )
    await update.message.reply_text(welcome_message, reply_markup=MAIN_KEYBOARD)
    logger.info("Ответ на /start отправлен")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message = update.message.text.strip().lower()
    logger.info(f"Получено сообщение от user_id={user_id}: {message}")

    if message == "/start":
        await start(update, context)
        return

    # Обработка текстовых команд
    if message == "пост":
        await update.message.reply_text("Укажи тему для поста (например, 'кофе'):")
        context.user_data['action'] = 'generate_post'
        return
    elif message == "рилс":
        await update.message.reply_text("Укажи тему для Reels (например, 'утренний ритуал'):")
        context.user_data['action'] = 'generate_reels'
        return
    elif message == "стратегия":
        await update.message.reply_text("Укажи цель стратегии (например, 'увеличить вовлечённость'):")
        context.user_data['action'] = 'generate_strategy'
        return
    elif message == "хештеги":
        await update.message.reply_text("Укажи тему для хэштегов (например, 'путешествия'):")
        context.user_data['action'] = 'generate_hashtags'
        return
    elif message == "а/б тест":
        await update.message.reply_text("Укажи, что ты хочешь протестировать (например, 'два варианта поста'):")
        context.user_data['action'] = 'ab_test'
        return

    # Если команда не распознана
    await update.message.reply_text("Выбери действие из кнопок ниже:", reply_markup=MAIN_KEYBOARD)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Обработка текстового сообщения от {update.message.from_user.id}: {update.message.text}")
    # Проверяем, есть ли сохранённое действие
    action = context.user_data.get('action')
    message = update.message.text.strip()

    if action:
        if action == 'generate_post':
            # Генерируем пост
            prompt = PROMPTS['post']['дружелюбный'].format(theme=message, template="короткий пост")
            try:
                text = generate_with_together(prompt)
                await update.message.reply_text(f"Вот твой пост:\n\n{text}")
            except Exception as e:
                logger.error(f"Ошибка при генерации поста: {e}")
                await update.message.reply_text("Произошла ошибка при генерации поста. Попробуй снова!")
            context.user_data['action'] = None
        elif action == 'generate_reels':
            # Генерируем идею для Reels
            prompt = f"Придумай идею для Reels на тему '{message}'."
            try:
                text = generate_with_together(prompt)
                await update.message.reply_text(f"Вот идея для Reels:\n\n{text}")
            except Exception as e:
                logger.error(f"Ошибка при генерации Reels: {e}")
                await update.message.reply_text("Произошла ошибка при генерации Reels. Попробуй снова!")
            context.user_data['action'] = None
        elif action == 'generate_strategy':
            # Генерируем стратегию на основе введённой цели
            goal = message
            prompt = f"Создай SMM-стратегию для достижения цели '{goal}' для аудитории 'молодёжь' на период 1 месяц."
            try:
                text = generate_with_together(prompt)
                await update.message.reply_text(f"Вот твоя стратегия:\n\n{text}")
            except Exception as e:
                logger.error(f"Ошибка при генерации стратегии: {e}")
                await update.message.reply_text("Произошла ошибка при генерации стратегии. Попробуй снова!")
            context.user_data['action'] = None
        elif action == 'generate_hashtags':
            # Генерируем хэштеги
            try:
                hashtags = generate_hashtags(message)
                await update.message.reply_text(f"Вот хэштеги:\n\n{hashtags}")
            except Exception as e:
                logger.error(f"Ошибка при генерации хэштегов: {e}")
                await update.message.reply_text("Произошла ошибка при генерации хэштегов. Попробуй снова!")
            context.user_data['action'] = None
        elif action == 'ab_test':
            # Генерируем варианты для А/Б теста
            prompt = f"Придумай два варианта для А/Б теста: {message}."
            try:
                text = generate_with_together(prompt)
                await update.message.reply_text(f"Вот варианты для А/Б теста:\n\n{text}")
            except Exception as e:
                logger.error(f"Ошибка при генерации А/Б теста: {e}")
                await update.message.reply_text("Произошла ошибка при генерации А/Б теста. Попробуй снова!")
            context.user_data['action'] = None
    else:
        # Если действия нет, просто обрабатываем сообщение
        await handle_message(update, context)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Вызов handle_voice")
    voice_file = await update.message.voice.get_file()
    file_path = f"voice_{update.message.message_id}.ogg"
    await voice_file.download_to_drive(file_path)
    await update.message.reply_text("Голосовые сообщения пока не поддерживаются.")
    os.remove(file_path)