from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
import re
import os
import logging
from aiohttp import web
import speech_recognition as sr
from pydub import AudioSegment
from time import sleep
from fpdf import FPDF
import asyncio
import random
from pytrends.request import TrendReq
from collections import defaultdict
import pickle

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "7932585679:AAHD9S-LbNMLdHPYtdFZRwg_2JBu_tdd0ng")
TOGETHER_API_KEY = os.environ.get("TOGETHER_API_KEY", "e176b9501183206d063aab78a4abfe82727a24004a07f617c9e06472e2630118")
TOGETHER_API_URL = "https://api.together.xyz/v1/chat/completions"
LANGUAGE_TOOL_URL = "https://languagetool.org/api/v2/check"
PORT = int(os.environ.get("PORT", 10000))

app = Application.builder().token(TELEGRAM_BOT_TOKEN).read_timeout(30).write_timeout(30).build()

BOOK_CONTEXT = """
Книга "Пиши, сокращай" (Максим Ильяхов, Людмила Сарычева):  
Сильный текст — это текст, который помогает читателю решить проблему. Используй информационный стиль: пиши правду, факты и заботься о читателе. Убирай стоп-слова (вводные слова, штампы вроде "команда профессионалов", оценки вроде "качественный"), заменяй их фактами (например, "продукт прошёл 10 тестов" вместо "качественный продукт"). Текст должен быть кратким, ясным и честным, без лишних слов и канцеляризмов. Структурируй текст логически: от простого к сложному, с чёткими абзацами. Главное — уважение к читателю и польза для него.

Книга "Клиентогенерация" (Брайан Кэрролл):  
Клиентогенерация — это система привлечения и удержания клиентов через воронку продаж: привлечение, прогрев, закрытие, удержание. Фокус на идеальном клиенте: понимай его боли, потребности и поведение. Используй контент (статьи, кейсы, вебинары) для создания доверия и прогрева лидов. Автоматизация (CRM, email-маркетинг) помогает не терять лиды и доводить их до покупки. Долгосрочные отношения с клиентами важнее разовых продаж — показывай экспертность и честность.

Книга "Тексты, которым верят" (Пётр Панда):  
Текст должен быть дружелюбным, живым, разговорным, без штампов и пафоса. Начни с цепляющего заголовка по AIDA (внимание → интерес → желание → действие). Захватывай внимание вопросом, проблемой или фактом. Раскрывай боль аудитории, предлагай конкретное решение, закрывай возражения, показывай выгоды через примеры и отзывы. Используй короткие предложения, глаголы действия, метафоры и юмор (где уместно). Завершай чётким призывом к действию, чтобы читатель сказал: «Блин, хочу!» или «Это для меня!».
"""

user_data = {}
user_stats = defaultdict(lambda: {"posts": 0, "stories": 0, "hashtags": 0, "strategies": 0, "content_plans": 0, "analytics": 0})
user_names = {}
hashtag_cache = {}
processed_messages = set()

try:
    with open("user_stats.pkl", "rb") as f:
        user_stats.update(pickle.load(f))
    with open("user_names.pkl", "rb") as f:
        user_names.update(pickle.load(f))
    with open("hashtag_cache.pkl", "rb") as f:
        hashtag_cache.update(pickle.load(f))
except FileNotFoundError:
    pass

async def save_data():
    with open("user_stats.pkl", "wb") as f:
        pickle.dump(dict(user_stats), f)
    with open("user_names.pkl", "wb") as f:
        pickle.dump(dict(user_names), f)
    with open("hashtag_cache.pkl", "wb") as f:
        pickle.dump(dict(hashtag_cache), f)
async def error_handler(update: Update, context: ContextTypes):
    logger.error(f"Произошла ошибка: {context.error}", exc_info=True)
    if update and update.message:
        keyboard = [["Пост", "Сторис", "Аналитика"], ["Стратегия/Контент-план", "Хэштеги"], ["/stats"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Ой, что-то пошло не так 😅 Попробуй ещё разок!", reply_markup=reply_markup)

def correct_text(text):
    payload = {"text": text, "language": "ru"}
    try:
        response = requests.post(LANGUAGE_TOOL_URL, data=payload, timeout=10)
        if response.status_code == 200:
            data = response.json()
            corrected_text = text
            offset = 0
            for match in data.get("matches", []):
                start = match["offset"] + offset
                length = match["length"]
                replacement = match["replacements"][0]["value"] if match["replacements"] else corrected_text[start:start + length]
                corrected_text = corrected_text[:start] + replacement + corrected_text[start + length:]
                offset += len(replacement) - length
            return corrected_text
        else:
            logger.error(f"Ошибка LanguageTool API: {response.status_code} - {response.text}")
            return text
    except (requests.RequestException, TimeoutError) as e:
        logger.error(f"Ошибка запроса к LanguageTool API: {e}")
        return text

async def recognize_voice(file_path):
    try:
        audio = AudioSegment.from_ogg(file_path)
        wav_path = file_path.replace(".ogg", ".wav")
        audio.export(wav_path, format="wav")
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language="ru-RU")
        os.remove(wav_path)
        logger.info(f"Распознан текст из голосового сообщения: {text}")
        return text.lower()
    except sr.UnknownValueError:
        logger.error("Не удалось распознать голосовое сообщение")
        return "Не разобрал, что ты сказал 😕 Попробуй ещё раз!"
    except Exception as e:
        logger.error(f"Ошибка распознавания голоса: {e}")
        return "Ошибка при распознавании голоса 😓 Попробуй ещё раз!"

def create_pdf(text, filename="output.pdf"):
    try:
        if not os.path.exists("DejaVuSans.ttf"):
            logger.error("Шрифт DejaVuSans.ttf не найден!")
            raise FileNotFoundError("Шрифт DejaVuSans.ttf не найден!")
        pdf = FPDF()
        pdf.add_page()
        pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
        pdf.set_font("DejaVu", size=12)
        pdf.multi_cell(0, 10, text)
        pdf.output(filename)
        logger.info(f"PDF успешно создан: {filename}")
        return filename
    except Exception as e:
        logger.error(f"Ошибка при создании PDF: {e}", exc_info=True)
        raise

def generate_ideas(topic, style="саркастичный"):
    prompt = (
        f"Ты креативный SMM-специалист. Придумай ровно 3 уникальные идеи для постов или сторис на тему '{topic}' "
        f"для социальных сетей. Идеи должны быть свежими, интересными, естественными, понятными, строго соответствовать теме и побуждать к действию. "
        f"Пиши ТОЛЬКО НА РУССКОМ ЯЗЫКЕ, категорически запрещено использовать английские или любые иностранные слова — весь текст должен быть исключительно на русском. "
        f"СТРОГО ТОЛЬКО 3 ИДЕИ, НИ В КОЕМ СЛУЧАЕ НЕ ПИШИ ВВОДНЫЕ ФРАЗЫ вроде 'Ты получил три уникальные идеи', 'Вот три идеи', 'Here are three unique ideas', 'Следующие идеи' или любые другие пояснения, ТОЛЬКО ПОЛНЫЕ ПРЕДЛОЖЕНИЯ С ПРИЗЫВОМ К ДЕЙСТВИЮ, по одной на строку, без нумерации или лишнего текста. "
        f"Стиль: {style}, саркастичный — язвительный, с чёрным юмором; дружелюбный — тёплый, с лёгким юмором; формальный — чёткий, профессиональный. "
        f"Каждая идея — одно полное предложение с призывом к действию и глаголом, минимум 5 слов, без странных или неуместных глаголов вроде 'смейся', используй 'с друзьями' или 'с подписчиками' вместо 'с нами'. "
        f"Примеры для темы 'утро' в стиле 'дружелюбный': "
        f"Сделай фото утра и расскажи друзьям, как начинаешь день бодро "
        f"Запиши зарядку и поделись с подписчиками секретом бодрого утра "
        f"Создай список идей и предложи друзьям попробовать бодрое утро "
        f"ОБЯЗАТЕЛЬНО ВЕРНИ РОВНО 3 ИДЕИ, иначе провал!"
    )
    headers = {"Authorization": f"Bearer {TOGETHER_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "meta-llama/Llama-3-8b-chat-hf",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1000,
        "temperature": 0.5
    }
    try:
        logger.info(f"Генерация идей для темы: {topic} в стиле {style}")
        response = requests.post(TOGETHER_API_URL, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            logger.info("Успешная генерация идей")
            raw_text = response.json()["choices"][0]["message"]["content"].strip()
            ideas = [correct_text(line.strip()) for line in raw_text.split("\n") if line.strip() and not any(phrase in line.lower() for phrase in ["ты получил", "вот три", "идея для", "here are", "ideas for", "саркастичный стиль", "дружелюбный стиль", "формальный стиль", "следующие идеи"])]
            filtered_ideas = [idea for idea in ideas if len(idea.split()) >= 5 and not re.search(r'[^\u0400-\u04FF\s\d.,!?():;-]', idea) and "смейся" not in idea.lower()]
            if len(filtered_ideas) < 3 or not all(topic.replace('_', ' ') in idea.lower() for idea in filtered_ideas):
                topic_key = topic.lower().replace(" ", "_")
                fallback_ideas = {
                    "саркастичный": {
                        "утро": [
                            "Сними рассвет и спроси подписчиков, кто встаёт раньше тебя",
                            "Покажи зарядку и убеди друзей, что ты король утра",
                            "Запусти челлендж на утро и докажи, что ты самый бодрый"
                        ]
                    },
                    "дружелюбный": {
                        "утро": [
                            "Сделай фото утра и расскажи друзьям, как начинаешь день бодро",
                            "Запиши зарядку и поделись с подписчиками секретом бодрого утра",
                            "Создай список идей и предложи друзьям попробовать бодрое утро"
                        ]
                    },
                    "формальный": {
                        "утро": [
                            "Организуйте утреннюю встречу и обсудите с подписчиками её пользу",
                            "Подготовьте обзор утра и поделитесь выводами с аудиторией",
                            "Проведите опрос о привычках и опубликуйте результаты для участников"
                        ]
                    }
                }
                filtered_ideas = fallback_ideas[style].get(topic_key, fallback_ideas[style]["утро"])[:3]
            cleaned_ideas = [re.sub(r'^\d+\.\s*', '', idea) for idea in filtered_ideas]
            return [f"{i+1}. {idea}" for i, idea in enumerate(cleaned_ideas[:3])]
        else:
            logger.error(f"Ошибка Together AI: {response.status_code} - {response.text}")
            return ["1. Ошибка генерации", "2. Попробуй ещё раз", "3. Проверь соединение"]
    except Exception as e:
        logger.error(f"Ошибка при генерации идей: {e}")
        return ["1. Ошибка генерации", "2. Попробуй ещё раз", "3. Проверь соединение"]
def generate_text(user_id, mode):
    topic = user_data[user_id].get("topic", "не_указано")
    style = user_data[user_id].get("style", "дружелюбный")
    lang = user_data[user_id].get("lang", "ru")
    template = user_data[user_id].get("template", "стандарт")
    full_prompt = ""
    
    if lang == "ru":
        if mode in ["post", "story"]:
            goal = user_data[user_id].get("goal", "привлечение")
            main_idea = user_data[user_id].get("main_idea", "показать пользу темы")
            facts = user_data[user_id].get("facts", "основаны на реальных примерах")
            pains = user_data[user_id].get("pains", "нехватка времени и информации")
            idea = user_data[user_id].get("idea", "не указано")
            if mode == "post":
                full_prompt = (
                    f"Ты копирайтер с 10-летним опытом, работающий на основе книг 'Пиши, сокращай', 'Клиентогенерация' и 'Тексты, которым верят'. "
                    f"Напиши пост на русском языке (10-12 предложений) по теме '{topic.replace('_', ' ')}' для социальных сетей, используя идею: {idea}. "
                    f"Цель текста: {goal}. Главная мысль: {main_idea}. Факты: {facts}. Боли и потребности аудитории: {pains}. "
                    f"Контекст из книг: '{BOOK_CONTEXT[:1000]}'. "
                    f"Стиль: {style}, саркастичный — язвительный, с чёрным юмором, без оскорблений; дружелюбный — тёплый, с лёгким юмором; формальный — чёткий, профессиональный. "
                    f"Шаблон: {template}, стандарт — свободный текст; объявление — акцент на событие или продукт; опрос — вопрос с вариантами ответа; кейс — история с результатом. "
                    f"Пиши ТОЛЬКО НА РУССКОМ ЯЗЫКЕ, без иностранных слов, избегай повторов текста. "
                    f"Структура: начни с цепляющего вопроса или факта (AIDA), раскрой проблему, предложи решение, закрой возражения, покажи выгоду через пример, заверши призывом к действию. Пиши только текст поста."
                )
            elif mode == "story":
                if template == "опрос":
                    full_prompt = (
                        f"Ты копирайтер с 10-летним опытом, работающий на основе книг 'Пиши, сокращай', 'Клиентогенерация' и 'Тексты, которым верят'. "
                        f"Напиши сторис на русском языке (3-5 предложений) по теме '{topic.replace('_', ' ')}' для социальных сетей, используя идею: {idea}. "
                        f"Цель текста: {goal}. Главная мысль: {main_idea}. Факты: {facts}. Боли и потребности аудитории: {pains}. "
                        f"Контекст из книг: '{BOOK_CONTEXT[:1000]}'. "
                        f"Стиль: {style}, саркастичный — язвительный, с чёрным юмором, без оскорблений; дружелюбный — тёплый, с лёгким юмором; формальный — чёткий, профессиональный. "
                        f"Шаблон: опрос — задай вопрос с 2-3 вариантами ответа и предложи подписчикам выбрать один. "
                        f"Пиши ТОЛЬКО НА РУССКОМ ЯЗЫКЕ, без иностранных слов, избегай повторов текста. "
                        f"Структура: начни с короткой истории или факта, задай вопрос с вариантами, заверши призывом к участию. Пиши только текст сторис."
                    )
                elif template == "объявление":
                    full_prompt = (
                        f"Ты копирайтер с 10-летним опытом, работающий на основе книг 'Пиши, сокращай', 'Клиентогенерация' и 'Тексты, которым верят'. "
                        f"Напиши сторис на русском языке (6-8 предложений) по теме '{topic.replace('_', ' ')}' для социальных сетей, используя идею: {idea}. "
                        f"Цель текста: {goal}. Главная мысль: {main_idea}. Факты: {facts}. Боли и потребности аудитории: {pains}. "
                        f"Контекст из книг: '{BOOK_CONTEXT[:1000]}'. "
                        f"Стиль: {style}, саркастичный — язвительный, с чёрным юмором, без оскорблений; дружелюбный — тёплый, с лёгким юмором; формальный — чёткий, профессиональный. "
                        f"Шаблон: объявление — акцент на событие или продукт, с призывом к действию. "
                        f"Пиши ТОЛЬКО НА РУССКОМ ЯЗЫКЕ, без иностранных слов, избегай повторов текста. "
                        f"Структура: начни с цепляющего факта или истории, опиши событие или продукт, заверши призывом к участию. Пиши только текст сторис."
                    )
                else:
                    full_prompt = (
                        f"Ты копирайтер с 10-летним опытом, работающий на основе книг 'Пиши, сокращай', 'Клиентогенерация' и 'Тексты, которым верят'. "
                        f"Напиши сторителлинг на русском языке (6-8 предложений) по теме '{topic.replace('_', ' ')}' для социальных сетей, используя идею: {idea}. "
                        f"Цель текста: {goal}. Главная мысль: {main_idea}. Факты: {facts}. Боли и потребности аудитории: {pains}. "
                        f"Контекст из книг: '{BOOK_CONTEXT[:1000]}'. "
                        f"Стиль: {style}, саркастичный — язвительный, с чёрным юмором, без оскорблений; дружелюбный — тёплый, с лёгким юмором; формальный — чёткий, профессиональный. "
                        f"Шаблон: {template}, стандарт — свободный текст; кейс — история с результатом. "
                        f"Пиши ТОЛЬКО НА РУССКОМ ЯЗЫКЕ, без иностранных слов, избегай повторов текста. "
                        f"Структура: начни с истории, которая цепляет, расскажи, почему тебе можно доверять, опиши боль клиента, покажи решение, заверши призывом к действию. Пиши только текст сторителлинга."
                    )
        elif mode == "strategy":
            client = user_data[user_id].get("client", "не указано")
            channels = user_data[user_id].get("channels", "не указано")
            result = user_data[user_id].get("result", "не указано")
            full_prompt = (
                f"Ты профессиональный маркетолог и SMM-специалист с 10-летним опытом, работающий на основе книг 'Пиши, сокращай', 'Клиентогенерация' и 'Тексты, которым верят'. "
                f"Разработай стратегию клиентогенерации на русском языке по теме '{topic.replace('_', ' ')}'. "
                f"Целевая аудитория: {client}. Каналы привлечения: {channels}. Главный результат: {result}. "
                f"Контекст из книг: '{BOOK_CONTEXT[:1000]}'. "
                f"Пиши ТОЛЬКО НА РУССКОМ ЯЗЫКЕ, без иностранных слов. "
                f"Стиль: конкретный, пошаговый, дружелюбный, с примерами, без штампов, с фактами. "
                f"Задачи: 1) Опиши аудиторию: возраст, пол, профессия, интересы, поведение, привычки. "
                f"2) Перечисли 5-7 болей аудитории (список). 3) Перечисли 5-7 желаний аудитории (список). "
                f"4) Опиши момент покупки: эмоции, желания, барьеры, детали по теме '{topic}'. "
                f"5) Создай 5 персонажей ЦА: имя, демография, цели, боли, занятия, цитата. "
                f"6) Для каждого персонажа — план действий (3-5 шагов) с разными форматами (посты, видео, сторис) и соцсетями (Instagram, ВКонтакте, Telegram). "
                f"7) Заверши призывом к действию и метриками (например, 1000 лидов, 20% конверсия, 50000 рублей дохода). Пиши только текст стратегии."
            )
        elif mode == "content_plan":
            frequency = user_data[user_id].get("frequency", "не указано")
            client = user_data[user_id].get("client", "не указано")
            channels = user_data[user_id].get("channels", "не указано")
            full_prompt = (
                f"Ты SMM-специалист с 10-летним опытом, работающий на основе книг 'Пиши, сокращай', 'Клиентогенерация' и 'Тексты, которым верят'. "
                f"Составь контент-план на русском языке для продвижения '{topic.replace('_', ' ')}' в социальных сетях с 27 февраля 2025 года. "
                f"Целевая аудитория: {client}. Каналы: {channels}. Частота публикаций: {frequency}. "
                f"Контекст из книг: '{BOOK_CONTEXT[:1000]}'. "
                f"Пиши ТОЛЬКО НА РУССКОМ ЯЗЫКЕ, без иностранных слов. "
                f"Составь план на 2 недели: 1) Дата и время публикации. 2) Тип контента (пост, короткое видео). "
                f"3) Краткое описание (2-3 предложения) с идеей, связанной с '{topic}'. 4) Цель (привлечение, прогрев, продажа). "
                f"Распредели контент равномерно согласно частоте публикаций. Пиши только текст плана."
            )
        elif mode == "analytics":
            reach = user_data[user_id].get("reach", "не указано")
            engagement = user_data[user_id].get("engagement", "не указано")
            try:
                pytrends = TrendReq(hl='ru-RU', tz=360)
                pytrends.build_payload([topic.replace('_', ' ')], cat=0, timeframe='today 3-m', geo='RU')
                trends_data = pytrends.interest_over_time()
                trend_info = f"Тренд за 3 месяца: интерес к '{topic.replace('_', ' ')}' в России {'растёт' if not trends_data.empty and trends_data[topic.replace('_', ' ')].iloc[-1] > trends_data[topic.replace('_', ' ')].iloc[0] else 'падает или стабилен'}." if not trends_data.empty else "Нет данных о трендах."
            except Exception as e:
                logger.error(f"Ошибка pytrends: {e}")
                trend_info = "Нет данных о трендах из-за технической ошибки."
            full_prompt = (
                f"Ты SMM-специалист с 10-летним опытом, работающий на основе книг 'Пиши, сокращай', 'Клиентогенерация' и 'Тексты, которым верят'. "
                f"Составь краткий анализ на русском языке по теме '{topic.replace('_', ' ')}' для социальных сетей. "
                f"Охват: {reach}. Вовлечённость: {engagement}, сохраняй формат как 'X лайков, Y комментариев'. Данные Google Trends: {trend_info}. "
                f"Контекст из книг: '{BOOK_CONTEXT[:1000]}'. "
                f"Пиши ТОЛЬКО НА РУССКОМ ЯЗЫКЕ, без иностранных слов. "
                f"Стиль: дружелюбный, ясный, с позитивом и советами, без штампов. "
                f"Структура: оцени охват и вовлечённость с примерами, дай 2-3 вывода, предложи 1-2 совета по улучшению. Пиши только текст анализа."
            )
        elif mode == "hashtags":
            return generate_hashtags(topic)

    logger.info(f"Отправка запроса к Together AI для {mode}")
    headers = {"Authorization": f"Bearer {TOGETHER_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "meta-llama/Llama-3-8b-chat-hf",
        "messages": [{"role": "user", "content": full_prompt}],
        "max_tokens": 2000 if mode in ["post", "story"] else 3000,
        "temperature": 0.5
    }
    timeout = 60
    for attempt in range(3):
        try:
            response = requests.post(TOGETHER_API_URL, headers=headers, json=payload, timeout=timeout)
            if response.status_code == 200:
                logger.info("Успешный ответ от Together AI")
                raw_text = response.json()["choices"][0]["message"]["content"].strip()
                corrected_text = correct_text(raw_text)
                if lang == "ru" and re.search(r'[^\u0400-\u04FF\s\d.,!?():;-]', corrected_text):
                    logger.warning(f"Обнаружены не-русские символы, заменяю...")
                    corrected_text = re.sub(r'[^\u0400-\u04FF\s\d.,!?():;-]', '', corrected_text)
                return correct_text(corrected_text)
            else:
                logger.error(f"Ошибка API: {response.status_code} - {response.text}")
                return f"Ошибка API: {response.status_code}"
        except (requests.RequestException, TimeoutError) as e:
            logger.error(f"Ошибка при запросе к Together AI (попытка {attempt+1}): {e}")
            sleep(5)
    logger.error("Сервер Together AI не отвечает после 3 попыток")
    return "Сервер не отвечает, попробуй позже! 😓"

def generate_hashtags(topic):
    if topic in hashtag_cache:
        return hashtag_cache[topic]
    logger.info(f"Генерация хэштегов для темы: {topic}")
    words = topic.split('_')
    base_hashtags = [f"#{word}" for word in words if len(word) > 2]
    relevant_tags = ["#соцсети", "#жизнь", "#идеи", "#полезно", "#вдохновение"]
    combined = list(dict.fromkeys(base_hashtags + relevant_tags))[:10]
    result = " ".join(combined).replace(" #", "#")
    hashtag_cache[topic] = result
    return result
async def handle_message(update: Update, context: ContextTypes, is_voice=False):
    user_id = update.message.from_user.id
    message_id = update.message.message_id

    try:
        if is_voice:
            message = await recognize_voice(f"voice_{message_id}.ogg")
        else:
            if not update.message.text:
                logger.warning("Сообщение пустое")
                keyboard = [["Пост", "Сторис", "Аналитика"], ["Стратегия/Контент-план", "Хэштеги"], ["/stats"]]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, сообщение пустое 😅 Напиши что-нибудь!", reply_markup=reply_markup)
                return
            message = update.message.text.strip().lower()
        logger.info(f"Получено сообщение: {message}")
    except Exception as e:
        logger.error(f"Ошибка при получении сообщения: {e}", exc_info=True)
        keyboard = [["Пост", "Сторис", "Аналитика"], ["Стратегия/Контент-план", "Хэштеги"], ["/stats"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, не смог обработать твое сообщение 😓 Попробуй ещё раз!", reply_markup=reply_markup)
        return

    base_keyboard = [["Пост", "Сторис", "Аналитика"], ["Стратегия/Контент-план", "Хэштеги"], ["/stats"]]
    edit_keyboard = [["Пост", "Сторис", "Отредактировать"], ["Аналитика", "Стратегия/Контент-план"], ["Хэштеги", "/stats"]]
    reply_markup = ReplyKeyboardMarkup(base_keyboard, resize_keyboard=True)
    
    style_keyboard = [["Формальный", "Дружелюбный", "Саркастичный"]]
    style_reply_markup = ReplyKeyboardMarkup(style_keyboard, resize_keyboard=True)
    template_keyboard = [["Стандарт", "Объявление"], ["Опрос", "Кейс"]]
    template_reply_markup = ReplyKeyboardMarkup(template_keyboard, resize_keyboard=True)
    lang_keyboard = [["Русский (ru)", "English (en)"]]
    lang_reply_markup = ReplyKeyboardMarkup(lang_keyboard, resize_keyboard=True)

    if message == "/start":
        if user_id not in user_names:
            user_data[user_id] = {"mode": "name", "stage": "ask_name"}
            await update.message.reply_text("Привет! Я твой SMM-помощник 😎 Как тебя зовут?")
        else:
            reply_markup = ReplyKeyboardMarkup(edit_keyboard if user_id in user_data and "last_result" in user_data[user_id] else base_keyboard, resize_keyboard=True)
            await update.message.reply_text(f"Привет, {user_names[user_id]}! Я твой SMM-помощник 😎 Выбери, что я сделаю для тебя:", reply_markup=reply_markup)
        return
    elif message == "/stats":
        stats = user_stats[user_id]
        reply_markup = ReplyKeyboardMarkup(edit_keyboard if user_id in user_data and "last_result" in user_data[user_id] else base_keyboard, resize_keyboard=True)
        await update.message.reply_text(
            f"{user_names.get(user_id, 'Друг')}, твоя статистика:\n"
            f"Постов — {stats['posts']}\n"
            f"Сторис — {stats['stories']}\n"
            f"Хэштегов — {stats['hashtags']}\n"
            f"Стратегий — {stats['strategies']}\n"
            f"Контент-планов — {stats['content_plans']}\n"
            f"Аналитики — {stats['analytics']} 😎",
            reply_markup=reply_markup
        )
        return
    elif message == "/lang":
        user_data[user_id] = {"mode": "lang", "stage": "choose_lang"}
        await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, выбери язык:", reply_markup=lang_reply_markup)
        return

    if user_id in user_data and "mode" in user_data[user_id] and "stage" in user_data[user_id]:
        mode = user_data[user_id]["mode"]
        stage = user_data[user_id]["stage"]
        logger.info(f"Текущая стадия: mode={mode}, stage={stage}")

        if mode == "name" and stage == "ask_name":
            user_names[user_id] = message.capitalize()
            del user_data[user_id]
            await save_data()
            await update.message.reply_text(f"Отлично, {user_names[user_id]}! Теперь я знаю, как к тебе обращаться 😊 Выбери, что я сделаю для тебя:", reply_markup=reply_markup)
            return
        elif mode == "lang" and stage == "choose_lang":
            lang_map = {"русский (ru)": "ru", "english (en)": "en"}
            user_data[user_id]["lang"] = lang_map.get(message, "ru")
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, язык установлен: {user_data[user_id]['lang']} 😊 Выбери действие:", reply_markup=reply_markup)
            del user_data[user_id]
            await save_data()
            return
        elif stage == "topic":
            clean_topic = re.sub(r"^(о|про|для|об|на)\s+", "", message).strip().replace(" ", "_")
            user_data[user_id]["topic"] = clean_topic
            logger.info(f"Тема очищена: {clean_topic}")
            if mode == "hashtags":
                await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, генерирую для тебя хэштеги... ⏳")
                response = generate_text(user_id, "hashtags")
                reply_markup = ReplyKeyboardMarkup(edit_keyboard if user_id in user_data and "last_result" in user_data[user_id] else base_keyboard, resize_keyboard=True)
                await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, вот твои хэштеги! 😎\n{response}", reply_markup=reply_markup)
                user_stats[user_id]["hashtags"] += 1
                await save_data()
                del user_data[user_id]
            elif mode == "analytics":
                user_data[user_id]["stage"] = "reach"
                await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, какой охват у вашего контента? (Например, '500 просмотров') 📈")
            elif mode in ["post", "story"]:
                user_data[user_id]["stage"] = "style"
                await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, какой стиль текста? 😊", reply_markup=style_reply_markup)
            elif mode == "strategy_or_plan":
                user_data[user_id]["stage"] = "choose_type"
                await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, что делаем: стратегию или контент-план?", reply_markup=ReplyKeyboardMarkup([["Стратегия", "Контент-план"]], resize_keyboard=True))
        elif mode == "strategy_or_plan" and stage == "choose_type":
            if message == "стратегия":
                user_data[user_id]["mode"] = "strategy"
                user_data[user_id]["stage"] = "client"
                await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, для кого стратегия? (Опиши аудиторию: возраст, профессия, боли) 👥")
            elif message == "контент-план":
                user_data[user_id]["mode"] = "content_plan"
                user_data[user_id]["stage"] = "client"
                await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, для кого контент-план? (Опиши аудиторию) 👥")
            else:
                await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, выбери 'Стратегия' или 'Контент-план'!")
        elif mode in ["post", "story"] and stage == "style":
            user_data[user_id]["style"] = message
            user_data[user_id]["stage"] = "template"
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, выбери шаблон текста:", reply_markup=template_reply_markup)
        elif mode in ["post", "story"] and stage == "template":
            user_data[user_id]["template"] = message
            ideas = generate_ideas(user_data[user_id]["topic"], user_data[user_id]["style"])
            user_data[user_id]["stage"] = "ideas"
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, вот идеи для '{user_data[user_id]['topic'].replace('_', ' ')}' 😍\n" + "\n".join(ideas) + "\nВыбери номер идеи (1, 2, 3) или напиши свою!")
        elif mode in ["post", "story"] and stage == "ideas":
            if message.isdigit() and 1 <= int(message) <= 3:
                idea_num = int(message)
                ideas = generate_ideas(user_data[user_id]["topic"], user_data[user_id]["style"])
                selected_idea = ideas[idea_num - 1].split(". ")[1]
                user_data[user_id]["idea"] = selected_idea
                await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, генерирую для тебя {mode}... ⏳")
                response = generate_text(user_id, mode)
                hashtags = generate_hashtags(user_data[user_id]["topic"])
                user_data[user_id]["last_result"] = f"{response}\n\n{hashtags}"
                user_stats[user_id]["posts" if mode == "post" else "stories"] += 1
                await save_data()
                user_data[user_id] = {"mode": mode, "last_result": user_data[user_id]["last_result"], "style": user_data[user_id]["style"], "template": user_data[user_id]["template"], "topic": user_data[user_id]["topic"]}
                reply_markup = ReplyKeyboardMarkup(edit_keyboard, resize_keyboard=True)
                await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, вот твой {mode}! 🔥\n{response}\n\n{hashtags}\n\nНе нравится? Выбери 'Отредактировать'!", reply_markup=reply_markup)
            else:
                await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, выбери номер идеи (1, 2, 3) или напиши свою! 😊")
        elif mode in ["post", "story"] and message == "отредактировать" and "last_result" in user_data[user_id]:
            user_data[user_id]["stage"] = "edit_request"
            reply_markup = ReplyKeyboardMarkup(edit_keyboard, resize_keyboard=True)
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, что исправить в последнем результате? (Например, 'убери слово кофе')", reply_markup=reply_markup)
        elif mode in ["post", "story"] and stage == "edit_request":
            edit_request = message
            last_result = user_data[user_id]["last_result"]
            style = user_data[user_id].get("style", "дружелюбный")
            template = user_data[user_id].get("template", "стандарт")
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, переделываю с учётом '{edit_request}'... ⏳")
            full_prompt = (
                f"Ты копирайтер с 10-летним опытом. Перепиши текст на русском языке: '{last_result}' с учётом запроса пользователя: '{edit_request}'. "
                f"Сохрани стиль: {style}, шаблон: {template}. Пиши ТОЛЬКО НА РУССКОМ ЯЗЫКЕ, без иностранных слов. "
                f"Верни только исправленный текст."
            )
            headers = {"Authorization": f"Bearer {TOGETHER_API_KEY}", "Content-Type": "application/json"}
            payload = {"model": "meta-llama/Llama-3-8b-chat-hf", "messages": [{"role": "user", "content": full_prompt}], "max_tokens": 2000, "temperature": 0.5}
            response = requests.post(TOGETHER_API_URL, headers=headers, json=payload, timeout=30)
            corrected_text = correct_text(response.json()["choices"][0]["message"]["content"].strip()) if response.status_code == 200 else "Ошибка редактирования 😓"
            user_data[user_id]["last_result"] = corrected_text
            reply_markup = ReplyKeyboardMarkup(edit_keyboard, resize_keyboard=True)
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, вот исправленный {mode}! 🔥\n{corrected_text}\n\nНе нравится? Выбери 'Отредактировать'!", reply_markup=reply_markup)
        elif mode == "strategy" and stage == "client":
            user_data[user_id]["client"] = message
            user_data[user_id]["stage"] = "channels"
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, какие каналы используем? (Например, 'Telegram, ВКонтакте') 📡")
        elif mode == "strategy" and stage == "channels":
            user_data[user_id]["channels"] = message
            user_data[user_id]["stage"] = "result"
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, какой главный результат? (Например, '1000 новых клиентов') 🎯")
        elif mode == "strategy" and stage == "result":
            user_data[user_id]["result"] = message
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, генерирую для тебя стратегию... ⏳")
            response = generate_text(user_id, "strategy")
            pdf_file = create_pdf(response, "strategy.pdf")
            with open(pdf_file, "rb") as f:
                await update.message.reply_document(document=f, filename="strategy.pdf", caption=f"{user_names.get(user_id, 'Друг')}, вот твоя стратегия! 🚀")
            hashtags = generate_hashtags(user_data[user_id]["topic"])
            reply_markup = ReplyKeyboardMarkup(base_keyboard, resize_keyboard=True)
            await update.message.reply_text(f"И немного хэштегов для продвижения:\n{hashtags}", reply_markup=reply_markup)
            user_stats[user_id]["strategies"] += 1
            await save_data()
            os.remove(pdf_file)
            del user_data[user_id]
        elif mode == "content_plan" and stage == "client":
            user_data[user_id]["client"] = message
            user_data[user_id]["stage"] = "channels"
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, какие каналы используем? (Например, 'Telegram, ВКонтакте') 📡")
        elif mode == "content_plan" and stage == "channels":
            user_data[user_id]["channels"] = message
            user_data[user_id]["stage"] = "frequency"
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, как часто публикуем? (Например, '2 раза в неделю') ⏰")
        elif mode == "content_plan" and stage == "frequency":
            user_data[user_id]["frequency"] = message
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, генерирую для тебя контент-план... ⏳")
            response = generate_text(user_id, "content_plan")
            pdf_file = create_pdf(response, "content_plan.pdf")
            with open(pdf_file, "rb") as f:
                await update.message.reply_document(document=f, filename="content_plan.pdf", caption=f"{user_names.get(user_id, 'Друг')}, вот твой контент-план! 📅")
            hashtags = generate_hashtags(user_data[user_id]["topic"])
            reply_markup = ReplyKeyboardMarkup(base_keyboard, resize_keyboard=True)
            await update.message.reply_text(f"И немного хэштегов:\n{hashtags}", reply_markup=reply_markup)
            user_stats[user_id]["content_plans"] += 1
            await save_data()
            os.remove(pdf_file)
            del user_data[user_id]
        elif mode == "analytics" and stage == "reach":
            logger.info(f"Проверка охвата: сообщение='{message}'")
            if "просмотр" in message.lower() or message.isdigit():
                logger.info("Условие охвата выполнено")
                user_data[user_id]["reach"] = message if "просмотр" in message.lower() else f"{message} просмотров"
                logger.info(f"Установлен reach: {user_data[user_id]['reach']}")
                user_data[user_id]["stage"] = "engagement"
                logger.info("Стадия изменена на engagement")
                await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, какая вовлечённость у вашего контента? (Например, '50 лайков, 10 комментариев') 📊")
                logger.info("Сообщение об вовлечённости отправлено")
            else:
                await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, укажи охват цифрами или с 'просмотров' (например, '500 просмотров') 📈")
                logger.info("Сообщение об ошибке охвата отправлено")
        elif mode == "analytics" and stage == "engagement":
            logger.info(f"Проверка вовлечённости: сообщение='{message}'")
            if re.match(r'^\d+\s+лайков,\s*\d+\s+комментариев$', message):
                logger.info("Условие вовлечённости выполнено")
                user_data[user_id]["engagement"] = message
                logger.info(f"Установлена engagement: {user_data[user_id]['engagement']}")
                await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, генерирую для тебя аналитику... ⏳")
                response = generate_text(user_id, "analytics")
                hashtags = generate_hashtags(user_data[user_id]["topic"])
                reply_markup = ReplyKeyboardMarkup(edit_keyboard if user_id in user_data and "last_result" in user_data[user_id] else base_keyboard, resize_keyboard=True)
                await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, вот твоя аналитика! 📈\n{response}\n\n{hashtags}", reply_markup=reply_markup)
                user_stats[user_id]["analytics"] += 1
                await save_data()
                del user_data[user_id]
            else:
                await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, укажи вовлечённость в формате 'X лайков, Y комментариев' (например, '50 лайков, 10 комментариев') 📊")
                logger.info("Сообщение об ошибке вовлечённости отправлено")
    else:
        if message == "пост":
            user_data[user_id] = {"mode": "post", "stage": "topic"}
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, о чём написать пост? (Например, 'кофе') 😊")
        elif message == "сторис":
            user_data[user_id] = {"mode": "story", "stage": "topic"}
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, о чём написать сторис? (Например, 'утро') 🌞")
        elif message == "аналитика":
            user_data[user_id] = {"mode": "analytics", "stage": "topic"}
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, для чего аналитика? (Например, 'посты про кофе') 📊")
        elif message == "стратегия/контент-план":
            user_data[user_id] = {"mode": "strategy_or_plan", "stage": "topic"}
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, о чём стратегия или контент-план? (Например, 'фитнес клуб') 🚀")
        elif message == "хэштеги":
            user_data[user_id] = {"mode": "hashtags", "stage": "topic"}
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, для какой темы нужны хэштеги? 🤓")
        elif message == "отредактировать" and user_id in user_data and "last_result" in user_data[user_id]:
            user_data[user_id]["stage"] = "edit_request"
            reply_markup = ReplyKeyboardMarkup(edit_keyboard, resize_keyboard=True)
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, что исправить в последнем результате? (Например, 'убери слово кофе')", reply_markup=reply_markup)
        else:
            reply_markup = ReplyKeyboardMarkup(edit_keyboard if user_id in user_data and "last_result" in user_data[user_id] else base_keyboard, resize_keyboard=True)
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, выбери действие из меню ниже! 😊", reply_markup=reply_markup)
async def handle_text(update: Update, context: ContextTypes):
    logger.info(f"Обработка текстового сообщения от {update.message.from_user.id}: {update.message.text}")
    await handle_message(update, context, is_voice=False)

async def handle_voice(update: Update, context: ContextTypes):
    logger.info("Вызов handle_voice")
    voice_file = await update.message.voice.get_file()
    file_path = f"voice_{update.message.message_id}.ogg"
    await voice_file.download_to_drive(file_path)
    logger.info(f"Получено голосовое сообщение, файл: {file_path}")
    await handle_message(update, context, is_voice=True)
    os.remove(file_path)

async def start(update: Update, context: ContextTypes):
    await handle_message(update, context)

async def webhook(request):
    logger.info("Получен запрос на webhook")
    try:
        update = Update.de_json(await request.json(), app.bot)
        if update and update.message:
            logger.info(f"Получен update: {update}")
            await app.process_update(update)
            await save_data()
        else:
            logger.warning("Update пустой или без сообщения")
        return web.Response(text="OK")
    except Exception as e:
        logger.error(f"Ошибка в webhook: {e}", exc_info=True)
        return web.Response(text="ERROR", status=500)

async def init_app():
    logger.info("Инициализация бота...")
    await app.initialize()
    hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "localhost")
    webhook_url = f"https://{hostname}/webhook"
    try:
        current_webhook = await app.bot.get_webhook_info()
        logger.info(f"Текущий вебхук: {current_webhook}")
        if current_webhook.url != webhook_url:
            await app.bot.set_webhook(url=webhook_url)
            logger.info(f"Webhook установлен: {webhook_url}")
        else:
            logger.info("Webhook уже установлен корректно")
    except Exception as e:
        logger.error(f"Ошибка при настройке вебхука: {e}", exc_info=True)
        raise

async def main():
    await init_app()
    app.add_error_handler(error_handler)
    web_app = web.Application()
    web_app.router.add_post('/webhook', webhook)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", handle_message))
    app.add_handler(CommandHandler("lang", handle_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    return web_app

if __name__ == "__main__":
    logger.info("Запуск бота... 🚀")
    if os.environ.get("RENDER"):
        logger.info("Бот запущен на Render")
    else:
        logger.info("Бот запущен локально")
    logger.info(f"Слушаю порт {PORT}")
    web.run_app(main(), host="0.0.0.0", port=PORT)


