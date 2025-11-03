import os
import re
import time
import logging
import threading
import requests
import sqlite3
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator, MyMemoryTranslator

# ============= НАСТРОЙКИ =============
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")  # например: "@finanosint"

# Пример источников (замените на свой список из 19)
SOURCES = [
    {"name": "The Economist", "url": "https://www.economist.com/rss/rss.xml"},
    {"name": "Foreign Policy", "url": "https://foreignpolicy.com/feed/"},
    # добавьте остальные 17 источников здесь
]

# Ключевые слова для фильтрации (регистронезависимо)
KEYWORDS = [
    r"russia", r"russian", r"kremlin", r"putin", r"moscow", r"ukraine", r"belarus",
    r"nato", r"nord stream", r"gazprom", r"rosneft", r"ruble", r"russian economy",
    r"sanction", r"russian military", r"wagner", r"prigozhin", r"lavrov", r"shoigu"
]

DB_PATH = "seen_links.db"
INTERVAL_SEC = 180  # 3 минуты
MAX_DB_SIZE = 5000

# ============= ЛОГИРОВАНИЕ =============
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger()

# ============= БАЗА ДАННЫХ =============
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS seen_links (
                link_hash TEXT PRIMARY KEY,
                processed_at TIMESTAMP
            )
        """)
        conn.commit()

def is_seen(link: str) -> bool:
    h = link.strip().rstrip('/').lower()
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("SELECT 1 FROM seen_links WHERE link_hash = ?", (h,))
        return cur.fetchone() is not None

def mark_seen(link: str):
    h = link.strip().rstrip('/').lower()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO seen_links (link_hash, processed_at) VALUES (?, ?)",
            (h, datetime.utcnow().isoformat())
        )
        conn.execute(f"DELETE FROM seen_links WHERE link_hash NOT IN (SELECT link_hash FROM seen_links ORDER BY processed_at DESC LIMIT {MAX_DB_SIZE})")
        conn.commit()

# ============= ПЕРЕВОД =============
def translate_to_russian(text: str) -> str:
    if not text.strip():
        return ""
    try:
        return GoogleTranslator(source='auto', target='ru').translate(text)
    except Exception as e1:
        log.warning(f"GoogleTranslator failed: {e1}")
        try:
            return MyMemoryTranslator(source='auto', target='ru').translate(text)
        except Exception as e2:
            log.warning(f"MyMemoryTranslator also failed: {e2}")
            return text  # возвращаем оригинал

# ============= ОЧИСТКА ТЕКСТА =============
def clean_text(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()

# ============= ПАРСИНГ RSS =============
def fetch_news():
    items = []
    for src in SOURCES:
        try:
            log.info(f"Проверка: {src['name']}")
            resp = requests.get(src["url"], timeout=15)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.content, "xml")
            for item in soup.find_all("item"):
                title = clean_text(item.title.get_text()) if item.title else ""
                link = (item.link and item.link.get_text().strip()) or ""
                if not title or not link:
                    continue
                link = link.split('?')[0].rstrip('/')

                if is_seen(link):
                    continue

                # Фильтрация по ключевым словам
                if not any(re.search(kw, title, re.IGNORECASE) for kw in KEYWORDS):
                    continue

                # Получение описания
                desc = ""
                desc_tag = item.find("description") or item.find("content:encoded")
                if desc_tag:
                    raw = BeautifulSoup(desc_tag.get_text(), "html.parser").get_text()
                    sentences = re.split(r'(?<=[.!?])\s+', raw.strip())
                    desc = sentences[0] if sentences else raw[:250]
                if not desc.strip():
                    continue

                ru_title = translate_to_russian(title)
                ru_desc = translate_to_russian(desc)

                # Экранирование для MarkdownV2
                def escape_md(text):
                    for c in r'_*[]()~`>#+-=|{}.!':
                        text = text.replace(c, '\\' + c)
                    return text

                safe_title = escape_md(ru_title)
                safe_desc = escape_md(ru_desc)
                prefix = f"[{src['name']}]"

                msg = f"{prefix}: {safe_title}\n\n{safe_desc}\n\n[Источник]({link})"
                items.append((msg, link))
        except Exception as e:
            log.error(f"Ошибка {src['name']}: {e}")
    return items

# ============= ОТПРАВКА В TELEGRAM =============
def send_to_telegram(text: str) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, data=payload, timeout=15)
        if r.status_code == 200:
            return True
        else:
            log.error(f"Telegram error: {r.status_code} {r.text}")
            return False
    except Exception as e:
        log.error(f"Telegram exception: {e}")
        return False

# ============= HEALTH CHECK =============
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        pass

def start_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

# ============= ОСНОВНОЙ ЦИКЛ =============
def main_loop():
    init_db()
    while True:
        try:
            news = fetch_news()
            sent = 0
            for msg, link in news:
                if send_to_telegram(msg):
                    mark_seen(link)
                    sent += 1
                time.sleep(1)
            log.info(f"✅ Цикл завершён. Отправлено: {sent}")
        except Exception as e:
            log.exception(f"Критическая ошибка в цикле: {e}")
        time.sleep(INTERVAL_SEC)

# ============= ЗАПУСК =============
if __name__ == "__main__":
    threading.Thread(target=start_server, daemon=True).start()
    log.info(f"🚀 Бот запущен. Интервал: {INTERVAL_SEC} сек. Канал: {CHANNEL_ID}")
    main_loop()
