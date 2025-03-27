from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from utils import check_subscription, generate_with_together, generate_hashtags, generate_pdf, PROMPTS, subscriptions  # Абсолютный импорт
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

THEME, STYLE, TEMPLATE, IDEAS, EDIT = range(5)
GOAL, AUDIENCE, PERIOD = range(3)

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [["Пост", "Рилс"], ["Стратегия", "Хештеги"], ["А/Б тест"]],
    resize_keyboard=True
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    check_subscription(user_id)

    welcome_message = (
        "Привет! Я SMM-помощник в создании контента. 🎉\n"
        "У тебя 3 дня бесплатного доступа к Полной версии! Попробуй сгенерировать пост, идеи для Reels или стратегию и контент план."
    )

    await update.message.reply_text(welcome_message, reply_markup=MAIN_KEYBOARD)

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
        await update.message.reply_text(message, reply_markup=ReplyKeyboardRemove())
    else:
        expiry_date = subscriptions[user_id].strftime("%Y-%m-%d") if subscriptions[user_id] else "навсегда"
        await update.message.reply_text(
            f"У тебя уже есть подписка: {subscriptions[user_id]} (до {expiry_date}).\n"
            "Хочешь продлить или изменить подписку? Напиши /podpiska.",
            reply_markup=ReplyKeyboardRemove()
        )

async def strategiya(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_subscription(user_id):
        await update.message.reply_text(
            "Твой пробный период истёк! Оформи подписку: /podpiska",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    if subscriptions[user_id] not in ["full", "lifetime"]:
        await update.message.reply_text(
            "Функция 'Стратегия' доступна только в Полной версии. Оформи подписку: /podpiska",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "Какая у тебя цель? Например: Увеличить вовлечённость, Привлечь подписчиков, Продать продукт.",
        reply_markup=ReplyKeyboardRemove()
    )
    return GOAL

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

    goal_lower = goal.lower()
    if "вовлечённость" in goal_lower:
        strategy_type = "engagement"
    elif "подписчиков" in goal_lower:
        strategy_type = "followers"
    elif "продать" in goal_lower or "продаж" in goal_lower:
        strategy_type = "sales"
    else:
        strategy_type = "engagement"

    strategy_prompt = PROMPTS.get("strategy", {}).get(strategy_type, "Составь SMM-стратегию. Аудитория: {audience}, период: {period}.")
    strategy_prompt = strategy_prompt.format(audience=audience, channels="Instagram, Telegram", result="увеличение вовлечённости")

    logger.info(f"Генерация стратегии для пользователя {update.effective_user.id}")
    strategy_text = generate_with_together(strategy_prompt)
    hashtags = generate_hashtags("мода")
    pdf_buffer = generate_pdf(strategy_text)

    await update.message.reply_document(
        document=pdf_buffer,
        filename=f"SMM_Strategy_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
        caption=f"Вот твоя SMM-стратегия и контент-план! 📄\n\n{hashtags}"
    )

    await update.message.reply_text("Что дальше?", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_subscription(user_id):
        await update.message.reply_text(
            "Твой пробный период истёк! Оформи подписку: /podpiska",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    text = update.message.text
    subscription_type = subscriptions.get(user_id, "lite")

    if text == "Пост":
        if subscription_type in ["lite", "full", "lifetime"]:
            await update.message.reply_text("О чём написать пост? (укажи тему)", reply_markup=ReplyKeyboardRemove())
            context.user_data['action'] = "generate_post"
            return THEME
        else:
            await update.message.reply_text("Эта функция доступна только с подпиской. Оформи: /podpiska", reply_markup=ReplyKeyboardRemove())
    elif text == "Рилс":
        if subscription_type in ["lite", "full", "lifetime"]:
            await update.message.reply_text("О чём снять Reels? (укажи тему)", reply_markup=ReplyKeyboardRemove())
            context.user_data['action'] = "generate_reels"
            return THEME
        else:
            await update.message.reply_text("Эта функция доступна только с подпиской. Оформи: /podpiska", reply_markup=ReplyKeyboardRemove())
    elif text == "Стратегия":
        await strategiya(update, context)
    elif text == "Хештеги":
        if subscription_type in ["lite", "full", "lifetime"]:
            await update.message.reply_text("Для какой темы сгенерировать хэштеги?", reply_markup=ReplyKeyboardRemove())
            context.user_data['action'] = "generate_hashtags"
            return THEME
        else:
            await update.message.reply_text("Эта функция доступна только с подпиской. Оформи: /podpiska", reply_markup=ReplyKeyboardRemove())
    elif text == "А/Б тест":
        await update.message.reply_text(
            "Функция А/Б теста пока в разработке. Скоро добавлю! 😊",
            reply_markup=ReplyKeyboardRemove()
        )
        await update.message.reply_text("Что дальше?", reply_markup=MAIN_KEYBOARD)
    else:
        await update.message.reply_text("Выбери действие из кнопок ниже:", reply_markup=MAIN_KEYBOARD)

async def theme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    context.user_data['theme'] = update.message.text

    action = context.user_data.get('action', 'generate_post')

    if action == "generate_post":
        if subscriptions[user_id] == "full":
            await update.message.reply_text("Какой стиль текста? Формальный, Дружелюбный, Саркастичный")
            return STYLE
        else:
            await update.message.reply_text("Выбери шаблон: Стандарт, Объявление, Опрос, Кейс")
            return TEMPLATE
    elif action == "generate_reels":
        theme = context.user_data['theme']
        style = "Дружелюбный"
        ideas = [
            f"Идея 1: Короткое видео с советом по теме {theme}",
            f"Идея 2: Трендовая съёмка на тему {theme}",
            f"Идея 3: Вопрос к аудитории про {theme}"
        ]
        context.user_data['ideas'] = ideas
        await update.message.reply_text("Вот несколько идей для Reels:\n" + "\n".join(ideas) + "\n\nВыбери идею (1, 2, 3)")
        return IDEAS
    elif action == "generate_hashtags":
        theme = context.user_data['theme']
        hashtags = generate_hashtags(theme)
        await update.message.reply_text(f"Вот хэштеги для темы '{theme}':\n{hashtags}")
        await update.message.reply_text("Что дальше?", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END

async def style(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['style'] = update.message.text
    await update.message.reply_text("Выбери шаблон: Стандарт, Объявление, Опрос, Кейс")
    return TEMPLATE

async def template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['template'] = update.message.text
    theme = context.user_data['theme']
    style = context.user_data.get('style', 'Дружелюбный').lower()
    template = context.user_data['template']

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
    ideas = context.user_data['ideas']

    if idea_number in ["1", "2", "3"]:
        idea = ideas[int(idea_number) - 1].split(": ")[1]
    else:
        idea = "Показать пользу темы"

    action = context.user_data.get('action', 'generate_post')
    if action == "generate_post":
        template = context.user_data['template']
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
        logger.info(f"Генерация поста для пользователя {update.effective_user.id}")
        result = generate_with_together(post_prompt)
        hashtags = generate_hashtags(theme)
        context.user_data['last_result'] = result
        await update.message.reply_text(f"Готовый пост:\n{result}\n\n{hashtags}\n\nЕсли хочешь отредактировать, напиши 'Отредактировать'")
        return EDIT
    elif action == "generate_reels":
        reels_prompt = f"Создай идею для Reels на тему {theme}. Опиши короткое видео, которое привлечёт внимание аудитории. Идея: {idea}."
        logger.info(f"Генерация Reels для пользователя {update.effective_user.id}")
        result = generate_with_together(reels_prompt)
        hashtags = generate_hashtags(theme)
        context.user_data['last_result'] = result
        await update.message.reply_text(f"Готовая идея для Reels:\n{result}\n\n{hashtags}\n\nЕсли хочешь отредактировать, напиши 'Отредактировать'")
        return EDIT

async def edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text.lower() == "отредактировать":
        await update.message.reply_text("Что исправить? (например, 'убери слово кофе')")
        return EDIT
    elif text.lower() == "отмена":
        await update.message.reply_text("Отменено. Что дальше?", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END
    else:
        edit_request = text
        last_result = context.user_data['last_result']
        style = context.user_data.get('style', 'Дружелюбный').lower()
        action = context.user_data.get('action', 'generate_post')

        edit_prompt = (
            f"Перепиши текст на русском языке: '{last_result}' с учётом запроса пользователя: '{edit_request}'. "
            f"Сохрани стиль: {style}. Пиши ТОЛЬКО НА РУССКОМ ЯЗЫКЕ, без иностранных слов. "
            f"Верни только исправленный текст."
        )

        logger.info(f"Редактирование {'поста' if action == 'generate_post' else 'Reels'} для пользователя {update.effective_user.id}")
        edited_result = generate_with_together(edit_prompt)
        context.user_data['last_result'] = edited_result

        await update.message.reply_text(
            f"Исправленный {'пост' if action == 'generate_post' else 'Reels'}:\n{edited_result}\n\n"
            f"Если нужно ещё что-то изменить, напиши 'Отредактировать', или 'Отмена' для завершения."
        )
        return EDIT

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено. Что дальше?", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END