import os
import json
import requests
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm
from io import BytesIO
import logging
import threading

logger = logging.getLogger(__name__)

# Глобальные переменные
subscriptions = {}
subscription_expiry = {}
trial_start = {}
DEVELOPER_ID = 477468896
state_lock = threading.Lock()  # Для защиты словарей

TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
TOGETHER_API_URL = "https://api.together.xyz/v1/chat/completions"

try:
    with open('prompts.json', 'r', encoding='utf-8') as f:
        PROMPTS = json.load(f)
except FileNotFoundError:
    logger.error("Файл prompts.json не найден")
    PROMPTS = {}

# Сохранение состояния в файл
def save_state():
    with state_lock:
        state = {
            "subscriptions": subscriptions,
            "subscription_expiry": {k: v.isoformat() if v else None for k, v in subscription_expiry.items()},
            "trial_start": {k: v.isoformat() if v else None for k, v in trial_start.items()}
        }
        try:
            with open("state.json", "w", encoding="utf-8") as f:
                json.dump(state, f)
            logger.info("Состояние успешно сохранено в state.json")
        except Exception as e:
            logger.error(f"Ошибка при сохранении состояния в state.json: {e}")

# Загрузка состояния из файла
def load_state():
    global subscriptions, subscription_expiry, trial_start
    try:
        with open("state.json", "r", encoding="utf-8") as f:
            state = json.load(f)
            subscriptions.update(state["subscriptions"])
            subscription_expiry.update({
                k: datetime.fromisoformat(v) if v else None
                for k, v in state["subscription_expiry"].items()
            })
            trial_start.update({
                k: datetime.fromisoformat(v) if v else None
                for k, v in state["trial_start"].items()
            })
        logger.info("Состояние успешно загружено из state.json")
    except FileNotFoundError:
        logger.info("Файл state.json не найден, начинаем с чистого состояния")
    except Exception as e:
        logger.error(f"Ошибка при загрузке состояния из state.json: {e}")

def generate_with_together(prompt):
    if not TOGETHER_API_KEY:
        logger.error("TOGETHER_API_KEY не установлен")
        return "Ошибка: API ключ для Together AI не настроен. 😔"
    headers = {
        "Authorization": f"Bearer {TOGETHER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "meta-llama/Llama-3-8b-chat-hf",
        "messages": [
            {"role": "system", "content": "Ты копирайтер с 10-летним опытом, работающий на русском языке."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 1000,
        "temperature": 0.7,
        "top_p": 0.9
    }
    try:
        logger.info(f"Отправка запроса к Together AI: {prompt[:50]}...")
        response = requests.post(TOGETHER_API_URL, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            result = response.json()
            return result["choices"][0]["message"]["content"].strip()
        else:
            logger.error(f"Ошибка Together AI: {response.status_code} - {response.text}")
            return "Не удалось сгенерировать текст. Попробуй позже! 😔"
    except Exception as e:
        logger.error(f"Ошибка при вызове Together AI: {e}")
        return "Не удалось сгенерировать текст. Попробуй позже! 😔"

def generate_hashtags(topic):
    words = topic.split()
    base_hashtags = [f"#{word}" for word in words if len(word) > 2]
    thematic_hashtags = {
        "мода": ["#мода", "#стиль", "#тренды", "#образ", "#вдохновение"],
        "кофе": ["#кофе", "#утро", "#энергия", "#вкус", "#напиток"],
        "фитнес": ["#фитнес", "#спорт", "#здоровье", "#мотивация", "#тренировки"]
    }
    relevant_tags = []
    topic_lower = topic.lower()
    for key in thematic_hashtags:
        if key in topic_lower:
            relevant_tags.extend(thematic_hashtags[key])
            break
    if not relevant_tags:
        relevant_tags = ["#соцсети", "#жизнь", "#идеи", "#полезно", "#вдохновение"]
    combined = list(dict.fromkeys(base_hashtags + relevant_tags))[:10]
    return " ".join(combined)

def check_subscription(user_id):
    logger.info(f"Проверка подписки для пользователя {user_id}")
    with state_lock:
        try:
            if user_id == DEVELOPER_ID:
                subscriptions[user_id] = "lifetime"
                subscription_expiry[user_id] = None
                save_state()
                logger.info(f"Пользователь {user_id} является разработчиком, подписка lifetime")
                return True
            if user_id not in subscriptions or subscriptions[user_id] == "none":
                if user_id not in trial_start:
                    trial_start[user_id] = datetime.now()
                    subscriptions[user_id] = "full"
                    subscription_expiry[user_id] = trial_start[user_id] + timedelta(days=3)
                    save_state()
                    logger.info(f"Пользователь {user_id} получил пробный период на 3 дня")
                    return True
                else:
                    current_time = datetime.now()
                    expiry_time = subscription_expiry[user_id]
                    logger.info(f"Сравнение времени: текущее {current_time}, истекает {expiry_time}")
                    if current_time > expiry_time:
                        subscriptions[user_id] = "none"
                        save_state()
                        logger.info(f"Пробный период пользователя {user_id} истёк")
                        return False
                    logger.info(f"Пробный период пользователя {user_id} ещё действует")
                    return True
            if subscriptions[user_id] in ["lite", "full"]:
                current_time = datetime.now()
                expiry_time = subscription_expiry[user_id]
                logger.info(f"Сравнение времени: текущее {current_time}, истекает {expiry_time}")
                if current_time > expiry_time:
                    subscriptions[user_id] = "none"
                    save_state()
                    logger.info(f"Подписка пользователя {user_id} истекла")
                    return False
                logger.info(f"Подписка пользователя {user_id} ещё действует")
            return True
        except Exception as e:
            logger.error(f"Ошибка в check_subscription: {e}")
            raise

def generate_pdf(strategy_text):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    
    try:
        pdfmetrics.registerFont(TTFont('DejaVuSans', 'DejaVuSans.ttf'))
        c.setFont('DejaVuSans', 12)
    except Exception as e:
        logger.error(f"Не удалось загрузить шрифт DejaVuSans: {e}. Используем стандартный шрифт.")
        c.setFont('Helvetica', 12)

    width, height = A4
    margin = 20 * mm
    y_position = height - margin

    c.setFont('DejaVuSans' if 'DejaVuSans' in pdfmetrics.getRegisteredFontNames() else 'Helvetica', 16)
    c.drawString(margin, y_position, "SMM-стратегия и контент-план")
    y_position -= 20 * mm

    c.setFont('DejaVuSans' if 'DejaVuSans' in pdfmetrics.getRegisteredFontNames() else 'Helvetica', 12)
    lines = strategy_text.split('\n')
    for line in lines:
        if y_position < margin:
            c.showPage()
            c.setFont('DejaVuSans' if 'DejaVuSans' in pdfmetrics.getRegisteredFontNames() else 'Helvetica', 12)
            y_position = height - margin
        c.drawString(margin, y_position, line)
        y_position -= 5 * mm

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer