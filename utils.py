import os
import requests
import logging
from datetime import datetime, timedelta
from fpdf import FPDF

logger = logging.getLogger(__name__)

subscriptions = {}

def check_subscription(user_id):
    if user_id not in subscriptions:
        subscriptions[user_id] = datetime.now() + timedelta(days=3)  # 3 дня пробного периода
    return subscriptions[user_id] > datetime.now()

def generate_with_together(prompt):
    api_key = os.getenv("TOGETHER_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "meta-llama/Llama-3-8b-chat-hf",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1000,
        "temperature": 0.5
    }
    try:
        response = requests.post("https://api.together.xyz/v1/chat/completions", headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"].strip()
        else:
            logger.error(f"Ошибка Together AI: {response.status_code} - {response.text}")
            return "Ошибка генерации текста."
    except Exception as e:
        logger.error(f"Ошибка при генерации текста: {e}")
        return "Ошибка генерации текста."

def generate_hashtags(topic):
    # Перенеси логику из старого generate_hashtags
    return "#хэштег1 #хэштег2 #хэштег3"

def generate_pdf(text):
    pdf = FPDF()
    pdf.add_page()
    pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
    pdf.set_font("DejaVu", size=12)
    pdf.multi_cell(0, 10, text)
    pdf_file = f"output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf.output(pdf_file)
    return pdf_file

PROMPTS = {
    "post": {
        "дружелюбный": "Создай пост на тему {theme} в формате {template}.",
        "саркастичный": "Создай пост на тему {theme} в формате {template} с сарказмом.",
        "формальный": "Создай пост на тему {theme} в формате {template} в формальном стиле."
    },
    "strategy": {
        "engagement": "Составь SMM-стратегию для увеличения вовлечённости. Аудитория: {audience}, период: {period}."
    }
}