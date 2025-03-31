import os
import logging
from fpdf import FPDF
from together import Together
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Словарь подписок
subscriptions = {}

# Промпты для генерации контента
PROMPTS = {
    'post': {
        'дружелюбный': "Напиши короткий пост на тему '{theme}' в дружелюбном стиле: {template}",
        'профессиональный': "Напиши короткий пост на тему '{theme}' в профессиональном стиле: {template}",
        'вдохновляющий': "Напиши короткий пост на тему '{theme}' в вдохновляющем стиле: {template}",
    },
    'strategy': {
        'engagement': "Создай SMM-стратегию для увеличения вовлечённости для аудитории '{audience}' на период '{period}'."
    }
}

def check_subscription(user_id):
    """Проверяет подписку пользователя и обновляет её статус."""
    if user_id not in subscriptions:
        # Даём 3 дня бесплатного доступа
        subscriptions[user_id] = {
            'start_date': datetime.now(),
            'end_date': datetime.now() + timedelta(days=3),
            'status': 'trial'
        }
    logger.info(f"Подписка пользователя {user_id}: {subscriptions[user_id]}")
    return subscriptions[user_id]

def generate_with_together(prompt):
    """Генерирует текст с помощью Together API."""
    client = Together(api_key=os.getenv("TOGETHER_API_KEY"))
    try:
        response = client.completions.create(
            model="meta-llama/Llama-3-8b-chat-hf",
            prompt=prompt,
            max_tokens=500,
            temperature=0.7,
        )
        return response.choices[0].text.strip()
    except Exception as e:
        logger.error(f"Ошибка при генерации текста с Together: {e}")
        raise

def generate_hashtags(theme):
    """Генерирует хэштеги на основе темы."""
    prompt = f"Сгенерируй 5-7 хэштегов на русском языке для темы '{theme}'."
    try:
        hashtags = generate_with_together(prompt)
        return hashtags
    except Exception as e:
        logger.error(f"Ошибка при генерации хэштегов: {e}")
        raise

def generate_pdf(text, pdf_path):
    """Генерирует PDF-файл из текста и возвращает путь к файлу."""
    try:
        pdf = FPDF()
        pdf.add_page()
        # Добавляем шрифт с поддержкой русского языка
        pdf.add_font('DejaVu', '', 'DejaVuSans.ttf', uni=True)
        pdf.set_font('DejaVu', '', 12)
        # Разбиваем текст на строки, чтобы избежать проблем с кодировкой
        lines = text.split('\n')
        for line in lines:
            # Обрабатываем кодировку для каждой строки
            pdf.multi_cell(0, 10, line.encode('latin-1', 'replace').decode('latin-1'))
        # Сохраняем PDF по указанному пути
        pdf.output(pdf_path)
        logger.info(f"PDF успешно создан: {pdf_path}")
        return pdf_path
    except Exception as e:
        logger.error(f"Ошибка при создании PDF: {e}")
        raise