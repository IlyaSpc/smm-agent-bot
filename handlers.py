from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from utils import check_subscription, generate_with_together, generate_hashtags, generate_pdf, PROMPTS, subscriptions
from datetime import datetime
import logging
import os
import re

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

def remove_english_text(text):
    """Удаляет строки, содержащие английские слова."""
    lines = text.split('\n')
    filtered_lines = []
    for line in lines:
        # Проверяем, есть ли в строке английские буквы
        if not re.search(r'[a-zA-Z]', line):
            filtered_lines.append(line)
        else:
            logger.info(f"Удалена строка с английским текстом: {line}")
    return '\n'.join(filtered_lines)

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
        context.user_data['action'] = 'strategy_goal'
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
            prompt = f"Сгенерируй три варианта короткого поста на русском языке на тему '{theme}' в стиле '{style}'. Весь текст должен быть строго на русском языке, без английских слов. Каждый вариант должен быть отделён пустой строкой."
            try:
                text = generate_with_together(prompt)
                # Удаляем английский текст, если он всё же появился
                text = remove_english_text(text)
                # Сохраняем варианты
                variants = [v.strip() for v in text.split('\n\n') if v.strip()]
                context.user_data['post_variants'] = variants
                if len(variants) != 3:
                    logger.warning(f"Сгенерировано {len(variants)} вариантов вместо 3: {text}")
                    await update.message.reply_text("Произошла ошибка: сгенерировано неправильное количество вариантов. Попробуй снова!", reply_markup=MAIN_KEYBOARD)
                    context.user_data['action'] = None
                    context.user_data['theme'] = None
                    return
                await update.message.reply_text(f"Вот твои посты:\n\n{text}\n\nВыбери вариант: 1, 2 или 3")
                context.user_data['action'] = 'post_select'
            except Exception as e:
                logger.error(f"Ошибка при генерации поста: {e}")
                await update.message.reply_text("Произошла ошибка при генерации поста. Попробуй снова!", reply_markup=MAIN_KEYBOARD)
                context.user_data['action'] = None
                context.user_data['theme'] = None
        elif action == 'post_select':
            # Обрабатываем выбор варианта поста
            variants = context.user_data.get('post_variants', [])
            try:
                choice = int(message) - 1
                if 0 <= choice < len(variants):
                    selected_post = variants[choice]
                    await update.message.reply_text(f"Ты выбрал:\n\n{selected_post}", reply_markup=MAIN_KEYBOARD)
                else:
                    await update.message.reply_text("Пожалуйста, выбери 1, 2 или 3.")
                    return  # Не сбрасываем action, чтобы пользователь мог выбрать снова
            except ValueError:
                await update.message.reply_text("Пожалуйста, выбери 1, 2 или 3.")
                return  # Не сбрасываем action, чтобы пользователь мог выбрать снова
            context.user_data['action'] = None
            context.user_data['post_variants'] = None
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
            prompt = f"Сгенерируй три варианта идей для Reels на русском языке на тему '{theme}' в стиле '{style}'. Весь текст должен быть строго на русском языке, без английских слов. Каждый вариант должен быть отделён пустой строкой."
            try:
                text = generate_with_together(prompt)
                text = remove_english_text(text)
                variants = [v.strip() for v in text.split('\n\n') if v.strip()]
                context.user_data['reels_variants'] = variants
                if len(variants) != 3:
                    logger.warning(f"Сгенерировано {len(variants)} вариантов вместо 3: {text}")
                    await update.message.reply_text("Произошла ошибка: сгенерировано неправильное количество вариантов. Попробуй снова!", reply_markup=MAIN_KEYBOARD)
                    context.user_data['action'] = None
                    context.user_data['theme'] = None
                    return
                await update.message.reply_text(f"Вот идеи для Reels:\n\n{text}\n\nВыбери вариант: 1, 2 или 3")
                context.user_data['action'] = 'reels_select'
            except Exception as e:
                logger.error(f"Ошибка при генерации Reels: {e}")
                await update.message.reply_text("Произошла ошибка при генерации Reels. Попробуй снова!", reply_markup=MAIN_KEYBOARD)
                context.user_data['action'] = None
                context.user_data['theme'] = None
        elif action == 'reels_select':
            # Обрабатываем выбор варианта Reels
            variants = context.user_data.get('reels_variants', [])
            try:
                choice = int(message) - 1
                if 0 <= choice < len(variants):
                    selected_reel = variants[choice]
                    await update.message.reply_text(f"Ты выбрал:\n\n{selected_reel}", reply_markup=MAIN_KEYBOARD)
                else:
                    await update.message.reply_text("Пожалуйста, выбери 1, 2 или 3.")
                    return
            except ValueError:
                await update.message.reply_text("Пожалуйста, выбери 1, 2 или 3.")
                return
            context.user_data['action'] = None
            context.user_data['reels_variants'] = None
            context.user_data['theme'] = None
        elif action == 'strategy_goal':
            # Сохраняем цель и запрашиваем ЦА
            context.user_data['goal'] = message
            await update.message.reply_text("Укажи целевую аудиторию (например, 'молодёжь 18-24'):")
            context.user_data['action'] = 'strategy_audience'
        elif action == 'strategy_audience':
            # Сохраняем ЦА и запрашиваем период
            context.user_data['audience'] = message
            await update.message.reply_text("Укажи период стратегии (например, '1 месяц'):")
            context.user_data['action'] = 'strategy_period'
        elif action == 'strategy_period':
            # Генерируем стратегию с контент-планом и отправляем в PDF
            goal = context.user_data.get('goal')
            audience = context.user_data.get('audience')
            period = message
            prompt = (
                f"Создай SMM-стратегию на русском языке для достижения цели '{goal}' для аудитории '{audience}' на период '{period}'. "
                f"Включи в стратегию: 1) Цели и аудиторию, 2) Типы контента, 3) Календарь контента, 4) Стратегию вовлечения, "
                f"5) Сотрудничество с инфлюенсерами, 6) Платную рекламу, 7) Метрики и оценку, 8) Контент-план на указанный период с конкретными идеями постов и сторис. "
                f"Весь текст должен быть строго на русском языке, без английских слов. Каждый раздел должен быть отделён пустой строкой."
            )
            try:
                text = generate_with_together(prompt)
                text = remove_english_text(text)
                # Генерируем PDF
                pdf_path = f"strategy_{update.effective_user.id}.pdf"
                generate_pdf(text, pdf_path)
                # Отправляем PDF
                with open(pdf_path, 'rb') as pdf_file:
                    await update.message.reply_document(document=pdf_file, caption="Вот твоя стратегия в PDF:", reply_markup=MAIN_KEYBOARD)
                os.remove(pdf_path)
            except Exception as e:
                logger.error(f"Ошибка при генерации стратегии: {e}")
                await update.message.reply_text("Произошла ошибка при генерации стратегии. Попробуй снова!", reply_markup=MAIN_KEYBOARD)
            context.user_data['action'] = None
            context.user_data['goal'] = None
            context.user_data['audience'] = None
        elif action == 'generate_hashtags':
            # Генерируем хэштеги
            try:
                hashtags = generate_hashtags(message)
                hashtags = remove_english_text(hashtags)
                await update.message.reply_text(f"Вот хэштеги:\n\n{hashtags}", reply_markup=MAIN_KEYBOARD)
            except Exception as e:
                logger.error(f"Ошибка при генерации хэштегов: {e}")
                await update.message.reply_text("Произошла ошибка при генерации хэштегов. Попробуй снова!", reply_markup=MAIN_KEYBOARD)
            context.user_data['action'] = None
        elif action == 'ab_test':
            # Генерируем варианты для А/Б теста
            prompt = f"Сгенерируй на русском языке два варианта для А/Б теста: {message}. Весь текст должен быть строго на русском языке, без английских слов."
            try:
                text = generate_with_together(prompt)
                text = remove_english_text(text)
                await update.message.reply_text(f"Вот варианты для А/Б теста:\n\n{text}", reply_markup=MAIN_KEYBOARD)
            except Exception as e:
                logger.error(f"Ошибка при генерации А/Б теста: {e}")
               