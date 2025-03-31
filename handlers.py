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
        start_date = datetime.now()
        end_date = start_date + timedelta(days=3)
        subscriptions[user_id] = {
            "start_date": start_date,
            "end_date": end_date,
            "status": "trial"
        }
        logger.info(f"Подписка пользователя {user_id}: {subscriptions[user_id]}")
    return subscriptions[user_id]

# Функция для генерации постов (БЕЗ await)
def generate_post(theme: str, style: str) -> list[str]:
    max_attempts = 3
    for attempt in range(max_attempts):
        prompt = (
            f"Сгенерируй ровно 3 варианта текста для поста в соцсетях на тему '{theme}' в {style} стиле. "
            f"Каждый вариант должен быть на русском языке, не длиннее 3 предложений. "
            f"Разделяй варианты двумя переносами строки (\\n\\n). Не добавляй лишние строки."
        )
        try:
            # УБРАН await (together_client не асинхронный)
            response = together_client.completions.create(
                model="meta-llama/Llama-3-8b-chat-hf",
                prompt=prompt,
                max_tokens=150,
                temperature=0.7,
                top_p=0.9,
            )
            variants = response.choices[0].text.strip().split("\n\n")
            variants = [v.strip() for v in variants if v.strip() and not any(word in v.lower() for word in ["empty", "lines"])]
            
            if len(variants) >= 3:
                return variants[:3]
            else:
                logger.warning(f"Попытка {attempt + 1}: Сгенерировано {len(variants)} вариантов вместо 3")
                if attempt == max_attempts - 1:
                    variants += ["Вариант не сгенерирован. Попробуйте снова! 😊"] * (3 - len(variants))
                    return variants
        except Exception as e:
            logger.error(f"Ошибка при генерации поста: {e}")
            if attempt == max_attempts - 1:
                return ["Ошибка генерации"] * 3
    return ["Ошибка генерации"] * 3

# Функция для генерации стратегии (БЕЗ await)
def generate_strategy(goal: str, audience: str, period: str) -> str:
    prompt = (
        f"Составь SMM-стратегию для достижения цели '{goal}' для аудитории '{audience}' на период '{period}'. "
        f"Стратегия должна быть полностью на русском языке, включать 5-7 пунктов, каждый пункт начинаться с '* '. "
        f"Не используй английские слова (Instagram → Инстаграм, Live → прямые эфиры)"
    )
    try:
        # УБРАН await
        response = together_client.completions.create(
            model="meta-llama/Llama-3-8b-chat-hf",
            prompt=prompt,
            max_tokens=300,
            temperature=0.7,
            top_p=0.9,
        )
        strategy = response.choices[0].text.strip()
        lines = strategy.split("\n")
        filtered = []
        for line in lines:
            if not any(word in line.lower() for word in ["live", "session", "instagram", "facebook"]):
                filtered.append(line)
        return "\n".join(filtered)
    except Exception as e:
        logger.error(f"Ошибка при генерации стратегии: {e}")
        return "Не удалось сгенерировать стратегию. Попробуйте снова! 😓"

# Функция для создания PDF
def create_pdf(content: str, filename: str):
    pdf = FPDF()
    pdf.add_page()
    pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
    pdf.set_font("DejaVu", "", 12)
    pdf.multi_cell(0, 10, content)
    pdf.output(filename)
    logger.info(f"PDF успешно создан: {filename}")

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Команда /start от {user_id}")
    check_subscription(user_id)
    await update.message.reply_text("Привет! Я твой SMM-помощник! Как тебя зовут?")

# Обработчик текстовых сообщений
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip().lower()
    logger.info(f"Сообщение от {user_id}: {text}")
    
    subscription = check_subscription(user_id)
    if subscription["end_date"] < datetime.now() and subscription["status"] == "trial":
        await update.message.reply_text("Пробный период закончился. Подпишитесь для продолжения!")
        return
    
    if "user_name" not in context.user_data:
        context.user_data["user_name"] = update.message.text
        await update.message.reply_text(
            f"Приятно познакомиться, {context.user_data['user_name']}! 🎉 У тебя 3 дня бесплатного доступа! "
            f"Что выберешь: пост или стратегию?"
        )
        return
    
    if "пост" in text:
        context.user_data["state"] = "post_theme"
        await update.message.reply_text("Укажи тему поста:")
    elif "стратегия" in text:
        context.user_data["state"] = "strategy_goal"
        await update.message.reply_text("Укажи цель стратегии:")
    elif context.user_data.get("state") == "post_theme":
        context.user_data["post_theme"] = text
        context.user_data["state"] = "post_style"
        await update.message.reply_text("Выбери стиль: дружелюбный/профессиональный/вдохновляющий")
    elif context.user_data.get("state") == "post_style":
        style = text
        theme = context.user_data["post_theme"]
        try:
            variants = generate_post(theme, style)
            response = "\n\n".join([f"{i+1}. {v}" for i, v in enumerate(variants)])
            await update.message.reply_text(f"Ваши варианты:\n\n{response}")
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            await update.message.reply_text("Произошла ошибка. Попробуйте снова.")
        finally:
            context.user_data["state"] = None
    elif context.user_data.get("state") == "strategy_goal":
        context.user_data["strategy_goal"] = text
        context.user_data["state"] = "strategy_audience"
        await update.message.reply_text("Укажи целевую аудиторию:")
    elif context.user_data.get("state") == "strategy_audience":
        context.user_data["strategy_audience"] = text
        context.user_data["state"] = "strategy_period"
        await update.message.reply_text("Укажи период (например, '1 месяц'):")
    elif context.user_data.get("state") == "strategy_period":
        period = text
        goal = context.user_data["strategy_goal"]
        audience = context.user_data["strategy_audience"]
        try:
            strategy = generate_strategy(goal, audience, period)
            filename = f"strategy_{user_id}.pdf"
            create_pdf(strategy, filename)
            with open(filename, "rb") as f:
                await update.message.reply_document(document=f, filename=filename)
            os.remove(filename)
        except Exception as e:
            logger.error(f"Ошибка стратегии: {e}")
            await update.message.reply_text("Ошибка генерации стратегии. Попробуйте позже.")
        finally:
            context.user_data["state"] = None

# Обработчик ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")
    await update.message.reply_text("Произошла ошибка. Попробуйте снова.")

# Основная функция запуска (исправленный вариант)
def main():
    application = Application.builder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_error_handler(error_handler)
    logger.info("Бот запущен")
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 80)),
        url_path="",
        webhook_url=f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/"
    )

if __name__ == "__main__":
    main()