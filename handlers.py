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

together_client = Together(api_key=os.getenv("TOGETHER_API_KEY"))
subscriptions = {}

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

# Генерация постов
async def generate_post(theme: str, style: str) -> list[str]:
    max_attempts = 3
    for attempt in range(max_attempts):
        prompt = (
            f"Сгенерируй ровно 3 варианта текста для поста в соцсетях на тему '{theme}' в {style} стиле. "
            f"Каждый вариант должен быть на русском языке, не длиннее 3 предложений. "
            f"Разделяй варианты двумя переносами строки (\n\n)."
        )
        try:
            response = together_client.completions.create(
                model="meta-llama/Llama-3-8b-chat-hf",
                prompt=prompt,
                max_tokens=150,
                temperature=0.7,
                top_p=0.9,
            )
            variants = response.choices[0].text.strip().split("\n\n")
            variants = [v.strip() for v in variants if v.strip()]
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

# Генерация стратегии
async def generate_strategy(goal: str, audience: str, period: str) -> str:
    prompt = (
        f"Составь SMM-стратегию для достижения цели '{goal}' для аудитории '{audience}' на период '{period}'. "
        f"Требования: 7-10 пунктов с маркером '* ', только русский язык, "
        f"используй российские платформы (ВК, Ютуб, ТикТок, Инстаграм). "
        f"Не используй английские слова (Instagram → Инстаграм, Live → прямые эфиры)."
    )
    try:
        response = together_client.completions.create(
            model="meta-llama/Llama-3-8b-chat-hf",
            prompt=prompt,
            max_tokens=400,
            temperature=0.6,
        )
        strategy = response.choices[0].text.strip()
        lines = strategy.split("\n")
        filtered = []
        for line in lines:
            if not any(word in line.lower() for word in ["live", "instagram", "facebook"]):
                filtered.append(line)
        return "\n".join(filtered)
    except Exception as e:
        logger.error(f"Ошибка стратегии: {e}")
        return "Не получилось сгенерировать стратегию"

# Генерация хештегов
async def generate_hashtags(theme: str) -> str:
    prompt = f"Сгенерируй 5-7 хэштегов на русском языке для темы '{theme}'."
    try:
        response = together_client.completions.create(
            model="meta-llama/Llama-3-8b-chat-hf",
            prompt=prompt,
            max_tokens=50,
            temperature=0.6,
        )
        hashtags = response.choices[0].text.strip()
        return hashtags
    except Exception as e:
        logger.error(f"Ошибка при генерации хештегов: {e}")
        return "Не удалось сгенерировать хештеги. Попробуйте снова!"

# Генерация идей для Рилсов
async def generate_reels_idea(theme: str) -> str:
    prompt = f"Сгенерируй идею для Рилса на тему '{theme}' в формате короткого текста и списка необходимых элементов."
    try:
        response = together_client.completions.create(
            model="meta-llama/Llama-3-8b-chat-hf",
            prompt=prompt,
            max_tokens=100,
            temperature=0.7,
        )
        idea = response.choices[0].text.strip()
        return idea
    except Exception as e:
        logger.error(f"Ошибка при генерации идеи для Рилса: {e}")
        return "Не удалось сгенерировать идею для Рилса. Попробуйте снова!"

# Генерация А/Б теста
async def generate_ab_test(goal: str) -> str:
    prompt = f"Составь два варианта контента для А/Б теста с целью '{goal}'. Каждый вариант должен быть уникальным и содержать описание и хэштеги."
    try:
        response = together_client.completions.create(
            model="meta-llama/Llama-3-8b-chat-hf",
            prompt=prompt,
            max_tokens=200,
            temperature=0.7,
        )
        ab_test = response.choices[0].text.strip()
        return ab_test
    except Exception as e:
        logger.error(f"Ошибка при генерации А/Б теста: {e}")
        return "Не удалось сгенерировать А/Б тест. Попробуйте снова!"

# Создание PDF
def create_pdf(content: str, filename: str):
    pdf = FPDF()
    pdf.add_page()
    pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
    pdf.set_font("DejaVu", "", 12)
    pdf.multi_cell(0, 10, content)
    pdf.output(filename)
    logger.info(f"PDF создан: {filename}")

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    check_subscription(user_id)
    await update.message.reply_text("Привет! Как тебя зовут?")

# Обработчик текстовых сообщений
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip().lower()
    logger.info(f"Сообщение от {user_id}: {text}")

    subscription = check_subscription(user_id)
    if subscription["end_date"] < datetime.now() and subscription["status"] == "trial":
        await update.message.reply_text("Пробный период закончился. Подпишитесь!")
        return

    if "user_name" not in context.user_data:
        context.user_data["user_name"] = update.message.text
        await update.message.reply_text(
            f"Приятно познакомиться, {context.user_data['user_name']}! 🎉 Выберите: пост, стратегия, хештеги, рилс или А/Б тест"
        )
        return

    if "пост" in text:
        context.user_data["state"] = "post_theme"
        await update.message.reply_text("Укажите тему поста:")
    elif "стратегия" in text:
        context.user_data["state"] = "strategy_goal"
        await update.message.reply_text("Укажите цель стратегии:")
    elif "хештеги" in text:
        context.user_data["state"] = "hashtags_theme"
        await update.message.reply_text("Укажите тему для генерации хештегов:")
    elif "рيلс" in text:
        context.user_data["state"] = "reels_theme"
        await update.message.reply_text("Укажите тему для идеи Рилса:")
    elif "а/б тест" in text or "аб тест" in text:
        context.user_data["state"] = "ab_test_goal"
        await update.message.reply_text("Укажите цель для А/Б теста:")
    elif context.user_data.get("state") == "post_theme":
        context.user_data["post_theme"] = text
        context.user_data["state"] = "post_style"
        await update.message.reply_text("Выберите стиль поста:")
    elif context.user_data.get("state") == "post_style":
        style = text
        theme = context.user_data["post_theme"]
        try:
            variants = await generate_post(theme, style)
            response = "\n\n".join([f"{i+1}. {v}" for i, v in enumerate(variants)])
            await update.message.reply_text(f"Ваши варианты:\n\n{response}")
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            await update.message.reply_text("Что-то пошло не так 😅")
        finally:
            context.user_data.pop("state", None)
    elif context.user_data.get("state") == "strategy_goal":
        context.user_data["strategy_goal"] = text
        context.user_data["state"] = "strategy_audience"
        await update.message.reply_text("Укажите целевую аудиторию:")
    elif context.user_data.get("state") == "strategy_audience":
        context.user_data["strategy_audience"] = text
        context.user_data["state"] = "strategy_period"
        await update.message.reply_text("Укажите период (например, '1 месяц'):")
    elif context.user_data.get("state") == "strategy_period":
        period = text
        try:
            strategy = await generate_strategy(
                context.user_data["strategy_goal"],
                context.user_data["strategy_audience"],
                period
            )
            filename = f"strategy_{user_id}.pdf"
            create_pdf(strategy, filename)
            with open(filename, "rb") as f:
                await update.message.reply_document(f)
            os.remove(filename)
        except Exception as e:
            logger.error(f"Ошибка стратегии: {e}")
            await update.message.reply_text("Ошибка. Попробуйте позже")
        finally:
            context.user_data.pop("state", None)
    elif context.user_data.get("state") == "hashtags_theme":
        theme = text
        try:
            hashtags = await generate_hashtags(theme)
            await update.message.reply_text(f"Ваши хештеги:\n{hashtags}")
        except Exception as e:
            logger.error(f"Ошибка хештегов: {e}")
            await update.message.reply_text("Что-то пошло не так 😅")
        finally:
            context.user_data.pop("state", None)
    elif context.user_data.get("state") == "reels_theme":
        theme = text
        try:
            idea = await generate_reels_idea(theme)
            await update.message.reply_text(f"Ваша идея для Рилса:\n{idea}")
        except Exception as e:
            logger.error(f"Ошибка Рилса: {e}")
            await update.message.reply_text("Что-то пошло не так 😅")
        finally:
            context.user_data.pop("state", None)
    elif context.user_data.get("state") == "ab_test_goal":
        goal = text
        try:
            ab_test = await generate_ab_test(goal)
            await update.message.reply_text(f"Ваши варианты для А/Б теста:\n{ab_test}")
        except Exception as e:
            logger.error(f"Ошибка А/Б теста: {e}")
            await update.message.reply_text("Что-то пошло не так 😅")
        finally:
            context.user_data.pop("state", None)
    else:
        await update.message.reply_text("Неизвестная команда. Пожалуйста, выберите из предложенных опций.")

# Обработчик ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")
    await update.message.reply_text("Произошла ошибка. Попробуйте позже")

# Запуск бота
def main():
    app = Application.builder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 80)),
        url_path="",
        webhook_url=f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/"
    )

if __name__ == "__main__":
    main()