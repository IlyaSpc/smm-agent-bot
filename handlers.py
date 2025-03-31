import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from together import Together
import os
from datetime import datetime, timedelta
from fpdf import FPDF
import re

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

def generate_post(theme: str, style: str) -> list[str]:
    max_attempts = 3
    for attempt in range(max_attempts):
        prompt = (
            f"Сгенерируй ровно 3 варианта текста для поста на тему '{theme}' в {style} стиле. "
            f"Каждый вариант на русском, до 3 предложений. Разделяй через 2 переноса строки."
        )
        try:
            response = together_client.completions.create(  # УБРАН await!
                model="meta-llama/Llama-3-8b-chat-hf",
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
                logger.warning(f"Попытка {attempt + 1}: Сгенерировано {len(variants)} вариантов")
                if attempt == max_attempts - 1:
                    variants += ["Вариант не сгенерирован. Попробуйте снова! 😊"] * (3 - len(variants))
                    return variants
        except Exception as e:
            logger.error(f"Ошибка генерации поста: {e}")
            if attempt == max_attempts - 1:
                return ["Ошибка генерации"] * 3
    return ["Ошибка генерации"] * 3

def generate_strategy(goal: str, audience: str, period: str) -> str:
    prompt = (
        f"Составь стратегию цели '{goal}' для '{audience}' за {period}. "
        f"5-7 пунктов с маркером '*', только русский язык. "
        f"Используй российские платформы (ВК, Ютуб, ТикТок, Инстаграм)."
    )
    try:
        response = together_client.completions.create(  # УБРАН await!
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

def create_pdf(content: str, filename: str):
    pdf = FPDF()
    pdf.add_page()
    pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
    pdf.set_font("DejaVu", "", 12)
    pdf.multi_cell(0, 10, content)  # УБРАНА кодировка latin-1
    pdf.output(filename)
    logger.info(f"PDF создан: {filename}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    check_subscription(user_id)
    await update.message.reply_text("Привет! Как тебя зовут?")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip().lower()
    subscription = check_subscription(user_id)
    
    if "user_name" not in context.user_data:
        context.user_data["user_name"] = update.message.text
        await update.message.reply_text(
            f"Приятно познакомиться, {context.user_data['user_name']}! 🎉 Выберите: пост или стратегия"
        )
        return
    
    if context.user_data.get("state") == "post_style":
        style = text
        theme = context.user_data["post_theme"]
        try:
            variants = generate_post(theme, style)  # УБРАН await!
            await update.message.reply_text(f"Ваши варианты:\n\n" + "\n\n".join(variants))
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            await update.message.reply_text("Что-то пошло не так 😅")
        finally:
            context.user_data.pop("state", None)
    
    elif context.user_data.get("state") == "strategy_period":
        period = text
        goal = context.user_data["strategy_goal"]
        audience = context.user_data["strategy_audience"]
        try:
            strategy = generate_strategy(goal, audience, period)  # УБРАН await!
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
    
    # Остальной код обработчика (логика состояний) остается без изменений
    # ...