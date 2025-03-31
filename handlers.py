import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from together import Together
import os
from datetime import datetime, timedelta
from fpdf import FPDF

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
            f"Каждый вариант должен быть на русском языке, не длиннее 5 предложений. "
            f"Разделяй варианты двумя переносами строки (\n\n)."
        )
        try:
            response = together_client.completions.create(
                model="meta-llama/Llama-2-7b-chat-hf",  # Бесплатная модель
                prompt=prompt,
                max_tokens=200,
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
                    while len(variants) < 3:
                        variants.append("Вариант не сгенерирован. Попробуйте снова!")
                    return variants
        except Exception as e:
            logger.error(f"Ошибка при генерации поста: {e}")
            if attempt == max_attempts - 1:
                return ["Ошибка генерации."] * 3
    return ["Ошибка генерации."] * 3

# Генерация стратегии
async def generate_strategy(goal: str, audience: str, period: str) -> str:
    prompt = (
        f"Составь детальную SMM-стратегию для цели '{goal}' для аудитории '{audience}' за {period}. "
        f"Требования: опиши нишу, целевую аудиторию (возраст, интересы), метрики успеха, формат контента, платформы (ВК, Ютуб, ТикТок, Инстаграм). "
        f"Стратегия должна быть полностью на русском языке, включать 7-10 пунктов, каждый пункт начинаться с '* '. "
        f"Не используй английские слова (Instagram → Инстаграм, Live → прямые эфиры)."
    )
    try:
        response = together_client.completions.create(
            model="meta-llama/Llama-2-7b-chat-hf",  # Бесплатная модель
            prompt=prompt,
            max_tokens=600,
            temperature=0.7,
        )
        strategy = response.choices[0].text.strip()
        lines = strategy.split("\n")
        filtered_lines = []
        for line in lines:
            if not any(word in line.lower() for word in ["live", "instagram", "facebook"]):
                filtered_lines.append(line)
        return "\n".join(filtered_lines)
    except Exception as e:
        logger.error(f"Ошибка при генерации стратегии: {e}")
        return "Не удалось сгенерировать стратегию. Попробуйте снова!"

# Создание PDF
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
    check_subscription(user_id)
    await update.message.reply_text(
        "Привет! Я твой SMM-помощник! 😊 Как тебя зовут?"
    )

# Обработчик текстовых сообщений
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.lower().strip()
    subscription = check_subscription(user_id)

    if "user_name" not in context.user_data:
        context.user_data["user_name"] = update.message.text
        await update.message.reply_text(
            f"Приятно познакомиться, {context.user_data['user_name']}! 🎉 У тебя 3 дня бесплатного доступа! "
            f"Что выберешь: пост, стратегия, хештеги, рилс или А/Б тест?",
            reply_markup=ReplyKeyboardMarkup([
                ["Создать пост", "Стратегия контента"],
                ["Генерация хештегов", "Идеи для Рилсов", "А/Б тест"]
            ], resize_keyboard=True)
        )
        return

    if "создать пост" in text:
        context.user_data["state"] = "post_theme"
        await update.message.reply_text("Укажи тему поста:")
    elif "стратегия" in text:
        context.user_data["state"] = "strategy_goal"
        await update.message.reply_text("Укажи цель стратегии:")
    elif context.user_data.get("state") == "post_theme":
        context.user_data["post_theme"] = text
        context.user_data["state"] = "post_style"
        await update.message.reply_text(
            "Выбери стиль:",
            reply_markup=ReplyKeyboardMarkup([
                ["Дружелюбный", "Профессиональный", "Вдохновляющий"]
            ], one_time_keyboard=True, resize_keyboard=True)  # Добавлен resize_keyboard
        )
    elif context.user_data.get("state") == "post_style":
        style = text
        theme = context.user_data["post_theme"]
        try:
            variants = await generate_post(theme, style)
            response = "\n\n".join([f"{i+1}. {v}" for i, v in enumerate(variants)])
            await update.message.reply_text(f"Вот твои варианты:\n\n{response}")
        except Exception as e:
            logger.error(f"Ошибка при генерации поста: {e}")
            await update.message.reply_text("Что-то пошло не так. Попробуйте снова.")
        finally:
            context.user_data.pop("state", None)
            context.user_data.pop("post_theme", None)
            await update.message.reply_text(  # Возврат в главное меню
                "Хочешь создать что-то ещё?",
                reply_markup=ReplyKeyboardMarkup([
                    ["Создать пост", "Стратегия контента"],
                    ["Генерация хештегов", "Идеи для Рилсов", "А/Б тест"]
                ], resize_keyboard=True)
            )
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
            logger.error(f"Ошибка при генерации стратегии: {e}")
            await update.message.reply_text("Что-то пошло не так. Попробуйте снова.")
        finally:
            context.user_data.pop("state", None)
            context.user_data.pop("strategy_goal", None)
            context.user_data.pop("strategy_audience", None)
            await update.message.reply_text(  # Возврат в главное меню
                "Хочешь создать что-то ещё?",
                reply_markup=ReplyKeyboardMarkup([
                    ["Создать пост", "Стратегия контента"],
                    ["Генерация хештегов", "Идеи для Рилсов", "А/Б тест"]
                ], resize_keyboard=True)
            )
    else:
        await update.message.reply_text("Неизвестная команда. Пожалуйста, выбери из предложенных опций.")

# Обработчик ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    await update.message.reply_text("Произошла ошибка. Попробуйте позже!")

# Основная функция запуска
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