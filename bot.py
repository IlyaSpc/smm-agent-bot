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

def create_pdf(text, filename="strategy.pdf"):
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

ddef generate_ideas(topic):
    prompt = (
        f"Ты креативный SMM-специалист. Придумай ровно 3 уникальные идеи для постов или сторис на тему '{topic}' "
        f"для социальных сетей. Идеи должны быть свежими, интересными, строго соответствовать теме и побуждать к действию. "
        f"Пиши ТОЛЬКО НА РУССКОМ ЯЗЫКЕ, категорически запрещено использовать английские или любые иностранные слова — весь текст должен быть исключительно на русском. "
        f"Каждая идея — одно короткое предложение с призывом к действию, обязательно с глаголом, без лишнего текста, вроде 'Вот три идеи...', и без нумерации. "
        f"Стиль — саркастичный, язвительный, с чёрным юмором, если тема позволяет. "
        f"Примеры для темы 'вред курения': "
        f"Сними свой кашель на видео и убеди всех, что курение — это модно "
        f"Похвастайся жёлтыми зубами в сторис и собери лайки от дантистов "
        f"Запусти челлендж 'Докажи, что куришь стильно' и вдохнови бросить эту дурь "
        f"Примеры для темы 'нетворкинг': "
        f"Похвастайся самым нелепым знакомством и удиви всех своими связями "
        f"Сфотографируй свою визитку в странном месте и собери лайки "
        f"Запусти марафон пяти рукопожатий за неделю и докажи свою профпригодность "
        f"ОБЯЗАТЕЛЬНО ВЕРНИ РОВНО 3 ИДЕИ, иначе провал!"
    )
    headers = {"Authorization": f"Bearer {TOGETHER_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "meta-llama/Llama-3-8b-chat-hf",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1000,  # Увеличиваем до 1000
        "temperature": 0.5
    }
    try:
        logger.info(f"Генерация идей для темы: {topic}")
        response = requests.post(TOGETHER_API_URL, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            logger.info("Успешная генерация идей")
            raw_text = response.json()["choices"][0]["message"]["content"].strip()
            ideas = [line.strip() for line in raw_text.split("\n") if line.strip() and not line.startswith("Вот") and not line.startswith("Здесь")]
            # Смягчаем фильтр: любой глагол
            filtered_ideas = [idea for idea in ideas if any(char.isalpha() for char in idea.split()[0])]  # Проверяем, что есть глагол
            ideas = filtered_ideas[:3] if len(filtered_ideas) >= 3 else filtered_ideas + ["Идея не сгенерирована"] * (3 - len(filtered_ideas))
            return [f"{i+1}. {idea}" for i, idea in enumerate(ideas)]
        else:
            logger.error(f"Ошибка Together AI: {response.status_code} - {response.text}")
            return ["1. Ошибка генерации", "2. Попробуй ещё раз", "3. Проверь соединение"]
    except Exception as e:
        logger.error(f"Ошибка при генерации идей: {e}")
        return ["1. Ошибка генерации", "2. Попробуй ещё раз", "3. Проверь соединение"]
async def handle_message(update: Update, context: ContextTypes, is_voice=False):
    user_id = update.message.from_user.id
    logger.info(f"Начало обработки сообщения от user_id={user_id}, is_voice={is_voice}")
    
    try:
        if is_voice:
            message = await recognize_voice(f"voice_{update.message.message_id}.ogg")
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

    keyboard = [["Пост", "Сторис", "Аналитика"], ["Стратегия/Контент-план", "Хэштеги"], ["/stats"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
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
            await update.message.reply_text(f"Привет, {user_names[user_id]}! Я твой SMM-помощник 😎 Выбери, что я сделаю для тебя:", reply_markup=reply_markup)
        return
    elif message == "/stats":
        stats = user_stats[user_id]
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
            del user_data[user_id]["mode"]
            del user_data[user_id]["stage"]
            await save_data()
            return
        elif stage == "topic":
            clean_topic = re.sub(r"^(о|про|для|об|на)\s+|[ие]$", "", message).strip().replace(" ", "_")
            user_data[user_id]["topic"] = clean_topic
            logger.info(f"Тема очищена: {clean_topic}")
            if mode == "hashtags":
                await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, генерирую для тебя хэштеги... ⏳")
                response = generate_text(user_id, "hashtags")
                await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, вот твои хэштеги! 😎\n{response}", reply_markup=reply_markup)
                user_stats[user_id]["hashtags"] += 1
                del user_data[user_id]
            elif mode == "analytics":
                user_data[user_id]["stage"] = "reach"
                await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, какой охват у вашего контента? (Например, '500 просмотров') 📈")
            elif mode in ["post", "story"]:
                user_data[user_id]["stage"] = "style"
                await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, какой стиль текста? 😊", reply_markup=style_reply_markup)
            elif mode == "strategy":
                user_data[user_id]["stage"] = "client"
                await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, для кого стратегия? (Опиши аудиторию: возраст, профессия, боли) 👥")
        elif mode in ["post", "story"] and stage == "style":
            logger.info(f"Выбран стиль: {message}")
            user_data[user_id]["style"] = message
            user_data[user_id]["stage"] = "template"
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, выбери шаблон текста:", reply_markup=template_reply_markup)
        elif mode in ["post", "story"] and stage == "template":
            logger.info(f"Выбран шаблон: {message}")
            user_data[user_id]["template"] = message
            ideas = generate_ideas(user_data[user_id]["topic"])
            user_data[user_id]["stage"] = "ideas"
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, вот идеи для '{user_data[user_id]['topic'].replace('_', ' ')}' 😍\n" + "\n".join(ideas) + "\nВыбери номер идеи (1, 2, 3...) или напиши свою!")
        elif mode in ["post", "story"] and stage == "ideas":
            logger.info(f"Выбор идеи: {message}")
            if message.isdigit() and 1 <= int(message) <= 3:
                idea_num = int(message)
                ideas = generate_ideas(user_data[user_id]["topic"])
                selected_idea = ideas[idea_num - 1].split(". ")[1]
                user_data[user_id]["idea"] = selected_idea
            else:
                user_data[user_id]["idea"] = message
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, генерирую для тебя {mode}... ⏳")
            response = generate_text(user_id, mode)
            hashtags = generate_hashtags(user_data[user_id]["topic"])
            user_data[user_id]["last_result"] = f"{response}\n\n{hashtags}"
            user_stats[user_id]["posts" if mode == "post" else "stories"] += 1
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, вот твой {mode}! 🔥\n{response}\n\n{hashtags}\n\nНе нравится? Напиши 'отредактировать'!", reply_markup=reply_markup)
            user_data[user_id]["stage"] = "edit"
        elif mode in ["post", "story"] and stage == "edit":
            if message == "отредактировать":
                user_data[user_id]["stage"] = "edit_request"
                await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, что исправить в последнем результате? (Например, 'убери слово кофе')")
            else:
                del user_data[user_id]
                await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, выбери новое действие! 😎", reply_markup=reply_markup)
        elif mode in ["post", "story"] and stage == "edit_request":
            edit_request = message
            last_result = user_data[user_id]["last_result"]
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, переделываю с учётом '{edit_request}'... ⏳")
            full_prompt = (
                f"Ты копирайтер с 10-летним опытом. Перепиши текст на русском языке: '{last_result}' с учётом запроса пользователя: '{edit_request}'. "
                f"Сохрани стиль: {style}, шаблон: {template}. Пиши ТОЛЬКО НА РУССКОМ ЯЗЫКЕ, без иностранных слов. "
                f"Верни только исправленный текст."
            )
            headers = {"Authorization": f"Bearer {TOGETHER_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": "meta-llama/Llama-3-8b-chat-hf",
                "messages": [{"role": "user", "content": full_prompt}],
                "max_tokens": 2000,
                "temperature": 0.5
            }
            response = requests.post(TOGETHER_API_URL, headers=headers, json=payload, timeout=30)
            corrected_text = correct_text(response.json()["choices"][0]["message"]["content"].strip()) if response.status_code == 200 else "Ошибка редактирования 😓"
            user_data[user_id]["last_result"] = corrected_text
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, вот исправленный {mode}! 🔥\n{corrected_text}\n\nНе нравится? Напиши 'отредактировать'!", reply_markup=reply_markup)
            user_data[user_id]["stage"] = "edit"
        elif mode == "strategy" and stage == "client":
            logger.info("Этап client")
            user_data[user_id]["client"] = message
            user_data[user_id]["stage"] = "channels"
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, какие каналы вы хотите использовать для привлечения? (Соцсети, реклама, содержание) 📱")
        elif mode == "strategy" and stage == "channels":
            logger.info("Этап channels")
            user_data[user_id]["channels"] = message
            user_data[user_id]["stage"] = "result"
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, какой главный результат вы хотите получить? (Прибыль, клиенты, узнаваемость) 🎯")
        elif mode == "strategy" and stage == "result":
            logger.info("Этап result, генерация стратегии")
            user_data[user_id]["result"] = message
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, генерирую для тебя стратегию... ⏳")
            try:
                response = generate_text(user_id, "strategy")
                hashtags = generate_hashtags(user_data[user_id]["topic"])
                topic = user_data[user_id]["topic"]
                pdf_file = create_pdf(response)
                with open(pdf_file, 'rb') as f:
                    await context.bot.send_document(
                        chat_id=update.message.chat_id,
                        document=f,
                        filename=f"Стратегия_{topic}.pdf",
                        caption=f"{user_names.get(user_id, 'Друг')}, вот твоя стратегия в PDF! 🔥\n\n{hashtags}",
                        reply_markup=reply_markup
                    )
                os.remove(pdf_file)
                logger.info(f"Стратегия успешно отправлена как PDF для user_id={user_id}")
                user_stats[user_id]["strategies"] += 1
                await asyncio.sleep(20)
                await context.bot.send_message(
                    chat_id=update.message.chat_id,
                    text=f"{user_names.get(user_id, 'Друг')}, хотите контент-план по этой стратегии? (Да/Нет) 😊",
                    reply_markup=reply_markup
                )
                user_data[user_id]["stage"] = "content_plan_offer"
            except Exception as e:
                logger.error(f"Ошибка при генерации стратегии или PDF: {e}", exc_info=True)
                await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, не удалось сгенерировать стратегию 😓 Попробуй ещё раз!", reply_markup=reply_markup)
        elif mode == "strategy" and stage == "content_plan_offer":
            if "да" in message:
                logger.info("Пользователь хочет контент-план")
                user_data[user_id]["stage"] = "frequency"
                await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, как часто хотите выпускать посты и короткие видео? (Например, '2 поста и 3 видео в неделю') 📅")
            else:
                logger.info("Пользователь отказался от контент-плана")
                await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, выбери новое действие! 😎", reply_markup=reply_markup)
                del user_data[user_id]
        elif mode == "strategy" and stage == "frequency":
            logger.info("Этап frequency, генерация контент-плана")
            user_data[user_id]["frequency"] = message
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, генерирую для тебя контент-план... ⏳")
            try:
                response = generate_text(user_id, "content_plan")
                hashtags = generate_hashtags(user_data[user_id]["topic"])
                topic = user_data[user_id]["topic"]
                try:
                    pdf_file = create_pdf(response)
                    with open(pdf_file, 'rb') as f:
                        await context.bot.send_document(
                            chat_id=update.message.chat_id,
                            document=f,
                            filename=f"Контент-план_{topic}.pdf",
                            caption=f"{user_names.get(user_id, 'Друг')}, вот твой контент-план в PDF! 🎉\n\n{hashtags}",
                            reply_markup=reply_markup
                        )
                    os.remove(pdf_file)
                    logger.info(f"Контент-план успешно отправлен как PDF для user_id={user_id}")
                    user_stats[user_id]["content_plans"] += 1
                except Exception as e:
                    logger.error(f"Ошибка создания PDF для контент-плана: {e}", exc_info=True)
                    await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, не удалось создать PDF 😕 Вот текст:\n{response[:4000]}\n\n{hashtags}", reply_markup=reply_markup)
            except Exception as e:
                logger.error(f"Ошибка при генерации контент-плана: {e}", exc_info=True)
                await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, не удалось сгенерировать контент-план 😓 Попробуй ещё раз!", reply_markup=reply_markup)
            del user_data[user_id]
        elif mode == "analytics" and stage == "reach":
            logger.info("Этап reach")
            user_data[user_id]["reach"] = message
            user_data[user_id]["stage"] = "engagement"
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, какая вовлечённость у вашего контента? (Например, '50 лайков, 10 комментариев') 📊")
        elif mode == "analytics" and stage == "engagement":
            logger.info("Этап engagement, генерация аналитики")
            user_data[user_id]["engagement"] = message
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, генерирую для тебя аналитику... ⏳")
            response = generate_text(user_id, "analytics")
            hashtags = generate_hashtags(user_data[user_id]["topic"])
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, вот твоя аналитика! 📈\n{response}\n\n{hashtags}", reply_markup=reply_markup)
            user_stats[user_id]["analytics"] += 1
            del user_data[user_id]
    else:
        if message == "пост":
            user_data[user_id] = {"mode": "post", "stage": "topic"}
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, о чём написать пост? (Например, 'кофе') 😊")
            return
        elif message == "сторис":
            user_data[user_id] = {"mode": "story", "stage": "topic"}
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, о чём написать сторис? (Например, 'утро') 🌞")
            return
        elif message == "аналитика":
            user_data[user_id] = {"mode": "analytics", "stage": "topic"}
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, для чего аналитика? (Например, 'посты про кофе') 📊")
            return
        elif message == "стратегия/контент-план":
            user_data[user_id] = {"mode": "strategy", "stage": "topic"}
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, о чём стратегия? (Например, 'фитнес клуб') 🚀")
            return
        elif message == "хэштеги":
            user_data[user_id] = {"mode": "hashtags", "stage": "topic"}
            await update.message.reply_text(f"{user_names.get(user_id, 'Друг')}, для какой темы нужны хэштеги? 🤓")
            return
        else:
            logger.info("Сообщение вне активной стадии")
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
        if update:
            logger.info(f"Получен update: {update}")
            await app.process_update(update)
            await save_data()
        else:
            logger.warning("Update пустой")
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
    logger.info(f"Слушаю порт {PORT}")
    web.run_app(main(), host="0.0.0.0", port=PORT)