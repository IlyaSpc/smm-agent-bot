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
    """Удаляет строки, содержащие английские слова, кроме названий платформ."""
    lines = text.split('\n')
    filtered_lines = []
    # Список исключений (названия платформ и термины)
    allowed_words = {'facebook', 'instagram', 'mention', 'hashtag', 'reels', 'stories', 'post', 'content', 'strategy'}
    for line in lines:
        # Ищем английские слова
        words = re.findall(r'\b[a-zA-Z]+\b', line.lower())
        # Проверяем, есть ли слова, которые не входят в список исключений
        has_forbidden_english = any(word not in allowed_words for word in words)
        if not has_forbidden_english:
            filtered_lines.append(line)
        else:
            logger.info(f"Удалена строка с английским текстом: {line}")
    return '\n'.join(filtered_lines)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Команда /start получена от пользователя {update.effective_user.id}")
    user_id = update.effective_user.id
    check_subscription(user_id)

    # Запрашиваем имя пользователя
    await update.message.reply_text("Привет! Я твой SMM-помощник, и я здесь, чтобы помочь тебе создавать крутой контент! 😊 Как тебя зовут?")
    context.user_data['action'] = 'ask_name'

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message = update.message.text.strip().lower()
    logger.info(f"Получено сообщение от user_id={user_id}: {message}")

    if message == "/start":
        await start(update, context)
        return

    # Обработка текстовых команд
    if message == "пост":
        await update.message.reply_text("Давай создадим пост! 🌟 Укажи тему (например, 'кофе'):")
        context.user_data['action'] = 'post_theme'
        return
    elif message == "рилс":
        await update.message.reply_text("Придумаем идеи для Reels! 🎥 Укажи тему (например, 'утренний ритуал'):")
        context.user_data['action'] = 'reels_theme'
        return
    elif message == "стратегия":
        await update.message.reply_text("Давай составим стратегию! 📈 Укажи цель (например, 'увеличить вовлечённость'):")
        context.user_data['action'] = 'strategy_goal'
        return
    elif message == "хештеги":
        await update.message.reply_text("Сгенерирую хэштеги для тебя! 🔖 Укажи тему (например, 'путешествия'):")
        context.user_data['action'] = 'generate_hashtags'
        return
    elif message == "а/б тест":
        await update.message.reply_text("Давай проведём А/Б тест! 🧪 Укажи, что хочешь протестировать (например, 'два варианта поста'):")
        context.user_data['action'] = 'ab_test'
        return

    # Если команда не распознана
    await update.message.reply_text("Выбери, что будем делать, из кнопок ниже! 😊", reply_markup=MAIN_KEYBOARD)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Обработка текстового сообщения от {update.message.from_user.id}: {update.message.text}")
    action = context.user_data.get('action')
    message = update.message.text.strip().lower()

    if action:
        if action == 'ask_name':
            # Сохраняем имя пользователя
            user_name = update.message.text.strip()
            context.user_data['user_name'] = user_name
            await update.message.reply_text(
                f"Приятно познакомиться, {user_name}! 🎉 У тебя 3 дня бесплатного доступа к Полной версии! "
                "Давай попробуем сгенерировать пост, идеи для Reels или стратегию с контент-планом. Что выберешь? 😊",
                reply_markup=MAIN_KEYBOARD
            )
            context.user_data['action'] = None
        elif action == 'post_theme':
            # Сохраняем тему и запрашиваем стиль
            context.user_data['theme'] = message
            await update.message.reply_text("Отлично! Теперь выбери стиль для поста: 😊", reply_markup=STYLE_KEYBOARD)
            context.user_data['action'] = 'post_style'
        elif action == 'post_style':
            # Генерируем три варианта поста в выбранном стиле
            theme = context.user_data.get('theme')
            style = message
            prompt = (
                f"Сгенерируй ровно три варианта короткого поста на русском языке на тему '{theme}' в стиле '{style}'. "
                f"Весь текст должен быть строго на русском языке, без английских слов. "
                f"Каждый вариант должен быть отделён двумя пустыми строками (\n\n). "
                f"Не добавляй заголовки вроде 'Вариант 1' или 'Вот три варианта поста', просто текст постов."
            )
            try:
                text = generate_with_together(prompt)
                text = remove_english_text(text)
                variants = [v.strip() for v in text.split('\n\n') if v.strip()]
                context.user_data['post_variants'] = variants
                if len(variants) != 3:
                    logger.warning(f"Сгенерировано {len(variants)} вариантов вместо 3: {text}")
                    await update.message.reply_text("Ой, что-то пошло не так! 😓 Сгенерировано неправильное количество вариантов. Давай попробуем снова?", reply_markup=MAIN_KEYBOARD)
                    context.user_data['action'] = None
                    context.user_data['theme'] = None
                    return
                formatted_text = "\n\n".join([f"**Вариант {i+1}**\n{v}" for i, v in enumerate(variants)])
                await update.message.reply_text(f"Вот твои посты! 🌟\n\n{formatted_text}\n\nКакой вариант выбираешь? Напиши 1, 2 или 3! 😊")
                context.user_data['action'] = 'post_select'
            except Exception as e:
                logger.error(f"Ошибка при генерации поста: {e}")
                await update.message.reply_text("Ой, что-то пошло не так при генерации поста! 😓 Давай попробуем снова?", reply_markup=MAIN_KEYBOARD)
                context.user_data['action'] = None
                context.user_data['theme'] = None
        elif action == 'post_select':
            # Обрабатываем выбор варианта поста
            variants = context.user_data.get('post_variants', [])
            try:
                choice = int(message) - 1
                if 0 <= choice < len(variants):
                    selected_post = variants[choice]
                    user_name = context.user_data.get('user_name', 'друг')
                    await update.message.reply_text(f"Отличный выбор, {user_name}! 🎉 Вот твой пост:\n\n{selected_post}", reply_markup=MAIN_KEYBOARD)
                else:
                    await update.message.reply_text("Пожалуйста, выбери 1, 2 или 3! 😊")
                    return  # Не сбрасываем action, чтобы пользователь мог выбрать снова
            except ValueError:
                await update.message.reply_text("Пожалуйста, выбери 1, 2 или 3! 😊")
                return  # Не сбрасываем action, чтобы пользователь мог выбрать снова
            context.user_data['action'] = None
            context.user_data['post_variants'] = None
            context.user_data['theme'] = None
        elif action == 'reels_theme':
            # Сохраняем тему и запрашиваем стиль
            context.user_data['theme'] = message
            await update.message.reply_text("Классная тема! Теперь выбери стиль для Reels: 😊", reply_markup=STYLE_KEYBOARD)
            context.user_data['action'] = 'reels_style'
        elif action == 'reels_style':
            # Генерируем три варианта идей для Reels в выбранном стиле
            theme = context.user_data.get('theme')
            style = message
            prompt = (
                f"Сгенерируй ровно три уникальных варианта идей для Reels на русском языке на тему '{theme}' в стиле '{style}'. "
                f"Каждая идея должна быть уникальной, не повторять предыдущие по смыслу и содержанию. "
                f"Весь текст должен быть строго на русском языке, без английских слов. "
                f"Каждый вариант должен быть отделён двумя пустыми строками (\n\n). "
                f"Не добавляй заголовки вроде 'Вариант 1' или 'Вот три варианта', просто текст идей."
            )
            try:
                text = generate_with_together(prompt)
                text = remove_english_text(text)
                variants = [v.strip() for v in text.split('\n\n') if v.strip()]
                context.user_data['reels_variants'] = variants
                if len(variants) != 3:
                    logger.warning(f"Сгенерировано {len(variants)} вариантов вместо 3: {text}")
                    await update.message.reply_text("Ой, что-то пошло не так! 😓 Сгенерировано неправильное количество идей. Давай попробуем снова?", reply_markup=MAIN_KEYBOARD)
                    context.user_data['action'] = None
                    context.user_data['theme'] = None
                    return
                formatted_text = "\n\n".join([f"**Вариант {i+1}**\n{v}" for i, v in enumerate(variants)])
                await update.message.reply_text(f"Вот идеи для Reels! 🎥\n\n{formatted_text}\n\nКакую идею выбираешь? Напиши 1, 2 или 3! 😊")
                context.user_data['action'] = 'reels_select'
            except Exception as e:
                logger.error(f"Ошибка при генерации Reels: {e}")
                await update.message.reply_text("Ой, что-то пошло не так при генерации идей для Reels! 😓 Давай попробуем снова?", reply_markup=MAIN_KEYBOARD)
                context.user_data['action'] = None
                context.user_data['theme'] = None
        elif action == 'reels_select':
            # Обрабатываем выбор варианта Reels
            variants = context.user_data.get('reels_variants', [])
            try:
                choice = int(message) - 1
                if 0 <= choice < len(variants):
                    selected_reel = variants[choice]
                    user_name = context.user_data.get('user_name', 'друг')
                    await update.message.reply_text(f"Супер выбор, {user_name}! 🎉 Вот твоя идея для Reels:\n\n{selected_reel}", reply_markup=MAIN_KEYBOARD)
                else:
                    await update.message.reply_text("Пожалуйста, выбери 1, 2 или 3! 😊")
                    return
            except ValueError:
                await update.message.reply_text("Пожалуйста, выбери 1, 2 или 3! 😊")
                return
            context.user_data['action'] = None
            context.user_data['reels_variants'] = None
            context.user_data['theme'] = None
        elif action == 'strategy_goal':
            # Сохраняем цель и запрашиваем ЦА
            context.user_data['goal'] = message
            await update.message.reply_text("Хорошая цель! 🎯 Теперь укажи целевую аудиторию (например, 'молодёжь 18-24'):")
            context.user_data['action'] = 'strategy_audience'
        elif action == 'strategy_audience':
            # Сохраняем ЦА и запрашиваем период
            context.user_data['audience'] = message
            await update.message.reply_text("Отлично! Теперь укажи период стратегии (например, '1 месяц'):")
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
                f"Весь текст должен быть строго на русском языке, без английских слов, кроме названий платформ (например, Instagram, Facebook). "
                f"Каждый раздел должен быть отделён пустой строкой."
            )
            try:
                text = generate_with_together(prompt)
                text = remove_english_text(text)
                # Генерируем PDF
                pdf_path = f"strategy_{update.effective_user.id}.pdf"
                generate_pdf(text, pdf_path)  # Теперь функция принимает два аргумента
                # Отправляем PDF
                with open(pdf_path, 'rb') as pdf_file:
                    user_name = context.user_data.get('user_name', 'друг')
                    await update.message.reply_document(document=pdf_file, caption=f"Вот твоя стратегия, {user_name}! 📈", reply_markup=MAIN_KEYBOARD)
                os.remove(pdf_path)
            except Exception as e:
                logger.error(f"Ошибка при генерации стратегии: {e}")
                await update.message.reply_text("Ой, что-то пошло не так при генерации стратегии! 😓 Давай попробуем снова?", reply_markup=MAIN_KEYBOARD)
            context.user_data['action'] = None
            context.user_data['goal'] = None
            context.user_data['audience'] = None
        elif action == 'generate_hashtags':
            # Генерируем хэштеги
            try:
                hashtags = generate_hashtags(message)
                hashtags = remove_english_text(hashtags)
                user_name = context.user_data.get('user_name', 'друг')
                await update.message.reply_text(f"Вот твои хэштеги, {user_name}! 🔖\n\n{hashtags}", reply_markup=MAIN_KEYBOARD)
            except Exception as e:
                logger.error(f"Ошибка при генерации хэштегов: {e}")
                await update.message.reply_text("Ой, что-то пошло не так при генерации хэштегов! 😓 Давай попробуем снова?", reply_markup=MAIN_KEYBOARD)
            context.user_data['action'] = None
        elif action == 'ab_test':
            # Генерируем варианты для А/Б теста
            prompt = f"Сгенерируй на русском языке два варианта для А/Б теста: {message}. Весь текст должен быть строго на русском языке, без английских слов, кроме названий платформ."
            try:
                text = generate_with_together(prompt)
                text = remove_english_text(text)
                user_name = context.user_data.get('user_name', 'друг')
                await update.message.reply_text(f"Вот варианты для А/Б теста, {user_name}! 🧪\n\n{text}", reply_markup=MAIN_KEYBOARD)
            except Exception as e:
                logger.error(f"Ошибка при генерации А/Б теста: {e}")
                await update.message.reply_text("Ой, что-то пошло не так при генерации А/Б теста! 😓 Давай попробуем снова?", reply_markup=MAIN_KEYBOARD)
            context.user_data['action'] = None
    else:
        await handle_message(update, context)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает голосовые сообщения."""
    logger.info("Вызов handle_voice")
    voice_file = await update.message.voice.get_file()
    file_path = f"voice_{update.message.message_id}.ogg"
    await voice_file.download_to_drive(file_path)
    user_name = context.user_data.get('user_name', 'друг')
    await update.message.reply_text(f"Прости, {user_name}, я пока не умею обрабатывать голосовые сообщения! 😅 Напиши текстом, и я помогу! 😊")
    os.remove(file_path)