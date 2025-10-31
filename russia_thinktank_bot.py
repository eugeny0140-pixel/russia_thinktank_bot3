# russia_thinktank_bot.py
import os
import json
import re
import time
import logging
import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
import schedule

# ================== НАСТРОЙКИ ==================
TELEGRAM_TOKEN = "  # ⚠️ СКОРО ИСТЕЧЁТ!
CHANNEL_ID = "@time_n_John"

# Только источники, которые реально работают (по логам)
SOURCES = [
    {"name": "Foreign Affairs", "url": "https://www.foreignaffairs.com/rss.xml"},
    {"name": "Reuters Institute", "url": "https://reutersinstitute.politics.ox.ac.uk/rss.xml"},
    {"name": "Bruegel", "url": "https://www.bruegel.org/rss.xml"},
    {"name": "E3G", "url": "https://www.e3g.org/feed/"},
]

# Ключевые слова — всё, что связано с РФ, Украиной, санкциями, геополитикой
KEYWORDS = [
    r"\brussia\b", r"\brussian\b", r"\bputin\b", r"\bmoscow\b", r"\bkremlin\b",
    r"\bukraine\b", r"\bukrainian\b", r"\bzelensky\b", r"\bkyiv\b", r"\bkiev\b",
    r"\bcrimea\b", r"\bdonbas\b", r"\bdonetsk\b", r"\bluhansk\b",
    r"\bsanction[s]?\b", r"\bembargo\b", r"\brestrict\b",
    r"\bgazprom\b", r"\bnord\s?stream\b",
    r"\bwagner\b", r"\bshoigu\b", r"\bmedvedev\b", r"\bpeskov\b", r"\blavrov\b",
    r"\bnato\b", r"\beuropa\b", r"\busa\b", r"\buk\b",
    r"\bwar\b", r"\bconflict\b", r"\bmilitary\b",
    r"\bruble\b", r"\beconomy\b", r"\benergy\b", r"\boil\b", r"\bgas\b",
]

SEEN_FILE = "seen_links.json"
MAX_SEEN = 3000
MAX_PER_RUN = 8

# ================== ЛОГИРОВАНИЕ ==================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("bot.log", encoding="utf-8"), logging.StreamHandler()]
)
log = logging.getLogger(__name__)

# ================== ФУНКЦИИ ==================

def load_seen_links():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f)[-MAX_SEEN:])
        except Exception as e:
            log.error(f"Ошибка чтения seen_links.json: {e}")
    return set()

def save_seen_link(link, seen):
    seen.add(link)
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen)[-MAX_SEEN:], f)

def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, data=payload, timeout=15)
        if r.status_code == 200:
            log.info("Отправлено в Telegram")
        else:
            log.error(f"Ошибка Telegram: {r.text}")
    except Exception as e:
        log.error(f"Исключение при отправке: {e}")

def clean_text(t):
    return re.sub(r"\s+", " ", t).strip()

def translate_to_russian(text):
    try:
        return GoogleTranslator(source='auto', target='ru').translate(text)
    except Exception as e:
        log.warning(f"Перевод не удался: {e}")
        return text

def get_summary(title):
    low = title.lower()
    if re.search(r"sanction|embargo|restrict", low):
        return "Введены новые санкции или ограничения."
    if re.search(r"war|attack|strike|bomb|conflict|military", low):
        return "Сообщается о военных действиях или ударах."
    if re.search(r"putin|kremlin|peskov|moscow", low):
        return "Заявление или действие со стороны Кремля."
    if re.search(r"economy|rubl?e|oil|gas|gazprom|nord\s?stream|energy", low):
        return "Новости экономики, нефти, газа или рубля."
    if re.search(r"diplomat|talks|negotiat|meeting|lavrov", low):
        return "Дипломатические переговоры или контакты."
    if re.search(r"wagner|shoigu|medvedev|defense", low):
        return "События с российскими военными или политиками."
    if re.search(r"ukraine|zelensky|kyiv|kiev|crimea|donbas", low):
        return "События, связанные с Украиной и прилегающими регионами."
    if re.search(r"nato|europa|european|germany|france|usa|uk", low):
        return "Реакция западных стран или НАТО на события с участием России."
    return "Аналитика, связанная с Россией или постсоветским пространством."

def fetch_rss_news():
    seen = load_seen_links()
    result = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    for src in SOURCES:
        if len(result) >= MAX_PER_RUN:
            break
        try:
            url = src["url"].strip()
            log.info(f"Парсинг: {src['name']}")
            resp = requests.get(url, timeout=25, headers=headers)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, "xml")

            for item in soup.find_all("item"):
                if len(result) >= MAX_PER_RUN:
                    break

                title = clean_text(item.title.get_text()) if item.title else ""
                link = (item.link.get_text() or item.guid.get_text()).strip() if item.link or item.guid else ""

                if not title or not link or link in seen:
                    continue

                # Фильтр: только если есть упоминание России/Украины/геополитики
                if not any(re.search(kw, title, re.IGNORECASE) for kw in KEYWORDS):
                    continue

                ru_title = translate_to_russian(title)
                summary = get_summary(title)

                # 🔗 ЗАГОЛОВОК — КЛИКАБЕЛЬНАЯ ССЫЛКА, РЕЗЮМЕ — ОБЫЧНЫЙ ТЕКСТ
                # Экранируем символы, которые ломают Markdown: [, ], (, )
                safe_title = ru_title.replace("[", "\\[").replace("]", "\\]").replace("(", "\\(").replace(")", "\\)")
                msg = f"[{safe_title}]({link})\n\n{summary}"
                result.append({"msg": msg, "link": link})

        except Exception as e:
            log.error(f"Ошибка при парсинге {src['name']}: {e}")

    return result

def job():
    log.info("Запуск проверки новостей по России...")
    news = fetch_rss_news()
    if not news:
        log.info("Нет релевантных публикаций.")
        return

    seen = load_seen_links()
    for item in news:
        send_to_telegram(item["msg"])
        save_seen_link(item["link"], seen)
        time.sleep(1.2)

# ================== ЗАПУСК БОТА ==================
if __name__ == "__main__":
    log.info("Бот запущен. Публикация только новостей, связанных с Россией.")
    job()
    schedule.every(30).minutes.do(job)

    while True:
        schedule.run_pending()
        time.sleep(1)

