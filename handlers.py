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

STYLE_KEYBOARD = ReplyKeyboardMarkup(
    [["Дружелюбный", "Профессиональный"], ["Вдохновляющий"]],
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
        context.user_data['action'] = 'post_theme'
        return
    elif message == "рилс":
        await update.message.reply_text("Укажи тему для Reels (например, 'утренний ритуал'):")
        context.user_data['action'] = 'reels_theme'
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
    action = context.user_data.get('action')
    message = update.message.text.strip().lower()

    if action:
        if action == 'post_theme':
            # Сохраняем тему и запрашиваем стиль
            context.user_data['theme'] = message
            await update.message.reply_text("Выбери стиль поста:", reply_markup=STYLE_KEYBOARD)
            context.user_data['action'] = 'post_style'
        elif action == 'post_style':
            # Генерируем три варианта поста в выбранном стиле
            theme = context.user_data.get('theme')
            style = message
            prompt = f"Сгенерируй три варианта короткого поста на русском языке на тему '{theme}' в стиле '{style}'."
            try:
                text = generate_with_together(prompt)
                await update.message.reply_text(f"Вот твои посты:\n\n{text}", reply_markup=MAIN_KEYBOARD)
            except Exception as e:
                logger.error(f"Ошибка при генерации поста: {e}")
                await update.message.reply_text("Произошла ошибка при генерации поста. Попробуй снова!", reply_markup=MAIN_KEYBOARD)
            context.user_data['action'] = None
            context.user_data['theme'] = None
        elif action == 'reels_theme':
            # Сохраняем тему и запрашиваем стиль
            context.user_data['theme'] = message
            await update.message.reply_text("Выбери стиль для Reels:", reply_markup=STYLE_KEYBOARD)
            context.user_data['action'] = 'reels_style'
        elif action == 'reels_style':
            # Генерируем три варианта идей для Reels в выбранном стиле
            theme = context.user_data.get('theme')
            style = message
            prompt = f"Сгенерируй три варианта идей для Reels на русском языке на тему '{theme}' в стиле '{style}'."
            try:
                text = generate_with_together(prompt)
                await update.message.reply_text(f"Вот идеи для Reels:\n\n{text}", reply_markup=MAIN_KEYBOARD)
            except Exception as e:
                logger.error(f"Ошибка при генерации Reels: {e}")
                await update.message.reply_text("Произошла ошибка при генерации Reels. Попробуй снова!", reply_markup=MAIN_KEYBOARD)
            context.user_data['action'] = None
            context.user_data['theme'] = None
        elif action == 'generate_strategy':
            # Генерируем стратегию с контент-планом и отправляем в PDF
            goal = message
            prompt = (
                f"Создай SMM-стратегию на русском языке для достижения цели '{goal}' для аудитории 'молодёжь' на период 1 месяц. "
                f"Включи в стратегию: 1) Цели и аудиторию, 2) Типы контента, 3) Календарь контента, 4) Стратегию вовлечения, "
                f"5) Сотрудничество с инфлюенсерами, 6) Платную рекламу, 7) Метрики и оценку, 8) Контент-план на 1 месяц с конкретными идеями постов и сторис."
            )
            try:
                text = generate_with_together(prompt)
                # Генерируем PDF
                pdf_path = f"strategy_{update.effective_user.id}.pdf"
                generate_pdf(text, pdf_path)
                # Отправляем PDF
                with open(pdf_path, 'rb') as pdf_file:
                    await update.message.reply_document(document=pdf_file, caption="Вот твоя стратегия в PDF:")
                os.remove(pdf_path)  # Удаляем временный файл
            except Exception as e:
                logger.error(f"Ошибка при генерации стратегии: {e}")
                await update.message.reply_text("Произошла ошибка при генерации стратегии. Попробуй снова!", reply_markup=MAIN_KEYBOARD)
            context.user_data['action'] = None
        elif action == 'generate_hashtags':
            # Генерируем хэштеги
            try:
                hashtags = generate_hashtags(message)
                await update.message.reply_text(f"Вот хэштеги:\n\n{hashtags}", reply_markup=MAIN_KEYBOARD)
            except Exception as e:
                logger.error(f"Ошибка при генерации хэштегов: {e}")
                await update.message.reply_text("Произошла ошибка при генерации хэштегов. Попробуй снова!", reply_markup=MAIN_KEYBOARD)
            context.user_data['action'] = None
        elif action == 'ab_test':
            # Генерируем варианты для А/Б теста
            prompt = f"Сгенерируй на русском языке два варианта для А/Б теста: {message}."
            try:
                text = generate_with_together(prompt)
                await update.message.reply_text(f"Вот варианты для А/Б теста:\n\n{text}", reply_markup=MAIN_KEYBOARD)
            except Exception as e:
                logger.error(f"Ошибка при генерации А/Б теста: {e}")
                await update.message.reply_text("Произошла ошибка при генерации А/Б теста. Попробуй снова!", reply_markup=MAIN_KEYBOARD)
            context.user_data['action'] = None
    else:
        await handle_message(update, context)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Вызов handle_voice")
    voice_file = await update.message.voice.get_file()
    file_path = f"voice_{update.message.message_id}.ogg"
    await voice_file.download_to_drive(file_path)
    await update.message.reply_text("Голосовые сообщения пока не поддерживаются.")
    os.remove(file_path)