import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from together import Together
import os
from datetime import datetime, timedelta
from fpdf import FPDF
import re

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация Together API
together_client = Together(api_key=os.getenv("TOGETHER_API_KEY"))

# Хранилище подписок пользователей
subscriptions = {}

# Функция для проверки и обновления подписки
def check_subscription(user_id: int) -> dict:
    if user_id not in subscriptions:
        # Новая подписка: 3 дня триала
        start_date = datetime.now()
        end_date = start_date + timedelta(days=3)
        subscriptions[user_id] = {
            "start_date": start_date,
            "end_date": end_date,
            "status": "trial"
        }
        logger.info(f"Подписка пользователя {user_id}: {subscriptions[user_id]}")
    return subscriptions[user_id]

# Функция для генерации постов
async def generate_post(theme: str, style: str) -> list[str]:
    max_attempts = 3  # Максимальное количество попыток генерации
    for attempt in range(max_attempts):
        # Уточнённый промпт для генерации ровно 3 вариантов
        prompt = (
            f"Сгенерируй ровно 3 варианта текста для поста в соцсетях на тему '{theme}' в {style} стиле. "
            f"Каждый вариант должен быть на русском языке, не длиннее 3 предложений. "
            f"Разделяй варианты двумя переносами строки (\n\n). "
            f"Не добавляй лишние строки или нумерацию."
        )
        try:
            response = await together_client.completions.create(
                model="meta-llama/Llama-3-8b-chat-hf",
                prompt=prompt,
                max_tokens=150,
                temperature=0.7,
                top_p=0.9,
            )
            # Разделяем текст на варианты
            variants = response.choices[0].text.strip().split("\n\n")
            # Удаляем пустые строки или строки на английском
            variants = [v.strip() for v in variants if v.strip() and not any(word in v.lower() for word in ["empty", "lines"])]
            # Проверяем количество вариантов
            if len(variants) == 3:
                logger.info(f"Успешно сгенерировано 3 варианта для темы '{theme}' в стиле '{style}'")
                return variants
            elif len(variants) > 3:
                # Если больше 3, берём первые 3
                logger.info(f"Сгенерировано {len(variants)} вариантов, берём первые 3: {variants}")
                return variants[:3]
            else:
                # Если меньше 3, пробуем снова
                logger.warning(f"Попытка {attempt + 1}: Сгенерировано {len(variants)} вариантов вместо 3: {variants}")
                if attempt == max_attempts - 1:
                    # Если последняя попытка, дополняем заглушками
                    while len(variants) < 3:
                        variants.append("Вариант не сгенерирован. Попробуйте снова! 😊")
                    return variants
        except Exception as e:
            logger.error(f"Ошибка при генерации поста: {e}")
            if attempt == max_attempts - 1:
                # Если последняя попытка, возвращаем заглушки
                return ["Вариант не сгенерирован. Попробуйте снова! 😊"] * 3
    return ["Вариант не сгенерирован. Попробуйте снова! 😊"] * 3  # На всякий случай

# Функция для генерации стратегии
async def generate_strategy(goal: str, audience: str, period: str) -> str:
    prompt = (
        f"Составь SMM-стратегию для достижения цели '{goal}' для аудитории '{audience}' на период '{period}'. "
        f"Стратегия должна быть полностью на русском языке, включать 5-7 пунктов, каждый пункт начинаться с '* '. "
        f"Не используй английские слова, такие как 'live', 'session', 'Instagram', 'Facebook' — "
        f"вместо них пиши 'прямые эфиры', 'сессии', 'Инстаграм', 'Фейсбук'."
    )
    try:
        response = await together_client.completions.create(
            model="meta-llama/Llama-3-8b-chat-hf",
            prompt=prompt,
            max_tokens=300,
            temperature=0.7,
            top_p=0.9,
        )
        strategy = response.choices[0].text.strip()
        # Дополнительная проверка на английский текст
        lines = strategy.split("\n")
        filtered_lines = []
        for line in lines:
            if any(word in line.lower() for word in ["live", "session", "instagram", "facebook"]):
                logger.info(f"Удалена строка с английским текстом: {line}")
                continue
            filtered_lines.append(line)
        return "\n".join(filtered_lines)
    except Exception as e:
        logger.error(f"Ошибка при генерации стратегии: {e}")
        return "Не удалось сгенерировать стратегию. Попробуйте снова! 😓"

# Функция для создания PDF
def create_pdf(content: str, filename: str):
    pdf = FPDF()
    pdf.add_page()
    pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
    pdf.set_font("DejaVu", "", 12)
    pdf.multi_cell(0, 10, content.encode('latin-1', 'replace').decode('latin-1'))
    pdf.output(filename)
    logger.info(f"PDF успешно создан: {filename}")

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Команда /start получена от пользователя {user_id}")
    check_subscription(user_id)
    await update.message.reply_text(
        "Привет! Я твой SMM-помощник, и я здесь, чтобы помочь тебе создавать крутой контент! 😊 Как тебя зовут?"
    )

# Обработчик текстовых сообщений
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.lower().strip()
    logger.info(f"Обработка текстового сообщения от {user_id}: {text}")

    # Проверяем подписку
    subscription = check_subscription(user_id)
    if subscription["end_date"] < datetime.now() and subscription["status"] == "trial":
        await update.message.reply_text("Ваш пробный период закончился. Подпишитесь, чтобы продолжить! 😊")
        return

    # Сохраняем имя пользователя
    if "user_name" not in context.user_data:
        context.user_data["user_name"] = update.message.text
        await update.message.reply_text(
            f"Приятно познакомиться, {context.user_data['user_name']}! 🎉 "
            f"У тебя 3 дня бесплатного доступа к Полной версии! "
            f"Давай попробуем сгенерировать пост, идеи для Reels или стратегию с контент-планом. Что выберешь? 😊"
        )
        return

    # Обработка ключевых слов
    if "пост" in text:
        logger.info(f"Получено сообщение от user_id={user_id}: пост")
        context.user_data["state"] = "post_theme"
        await update.message.reply_text("Давай создадим пост! 🌟 Укажи тему (например, 'кофе'):")
    elif "стратегия" in text:
        logger.info(f"Получено сообщение от user_id={user_id}: стратегия")
        context.user_data["state"] = "strategy_goal"
        await update.message.reply_text("Давай составим стратегию! 📈 Укажи цель (например, 'увеличить вовлечённость'):")
    elif context.user_data.get("state") == "post_theme":
        context.user_data["post_theme"] = update.message.text
        context.user_data["state"] = "post_style"
        await update.message.reply_text("Отлично! Теперь выбери стиль для поста: 😊")
    elif context.user_data.get("state") == "post_style":
        style = update.message.text
        theme = context.user_data.get("post_theme")
        try:
            variants = await generate_post(theme, style)
            response = "\n\n".join(variants)
            await update.message.reply_text(f"Вот твои варианты постов:\n\n{response}")
        except Exception as e:
            logger.error(f"Ошибка при генерации поста: {e}")
            await update.message.reply_text("Ой, что-то пошло не так! 😓 Давай попробуем снова?")
        finally:
            context.user_data["state"] = None
    elif context.user_data.get("state") == "strategy_goal":
        context.user_data["strategy_goal"] = update.message.text
        context.user_data["state"] = "strategy_audience"
        await update.message.reply_text("Хорошая цель! 🎯 Теперь укажи целевую аудиторию (например, 'молодёжь 18-24'):")
    elif context.user_data.get("state") == "strategy_audience":
        context.user_data["strategy_audience"] = update.message.text
        context.user_data["state"] = "strategy_period"
        await update.message.reply_text("Отлично! Теперь укажи период стратегии (например, '1 месяц'):")
    elif context.user_data.get("state") == "strategy_period":
        period = update.message.text
        goal = context.user_data.get("strategy_goal")
        audience = context.user_data.get("strategy_audience")
        try:
            strategy = await generate_strategy(goal, audience, period)
            # Создаём PDF
            filename = f"strategy_{user_id}.pdf"
            create_pdf(strategy, filename)
            # Отправляем PDF
            with open(filename, "rb") as f:
                await update.message.reply_document(document=f, filename=filename)
            # Удаляем файл после отправки
            os.remove(filename)
        except Exception as e:
            logger.error(f"Ошибка при генерации стратегии: {e}")
            await update.message.reply_text("Ой, что-то пошло не так! 😓 Давай попробуем снова?")
        finally:
            context.user_data["state"] = None

# Функция для обработки ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.message:
        await update.message.reply_text("Произошла ошибка. Попробуйте снова! 😓")

# Основная функция для запуска бота
def main():
    # Инициализация бота
    application = Application.builder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()

    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_error_handler(error_handler)

    # Запускаем бот
    logger.info("Запуск бота... 🚀")
    application.run_webhook(
        listen="0.0.0.0",
        port=80,
        url_path="",
        webhook_url=f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/"
    )

if __name__ == "__main__":
    main()