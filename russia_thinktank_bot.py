import os
import re
import time
import logging
import threading
import requests
import sqlite3
import hashlib
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator, MyMemoryTranslator

# ============= НАСТРОЙКИ =============
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenvy(, "@time_n_John", "@finanosint")  # ← имя переменной окружения!

# Список источников — только рабочие RSS/Atom фиды
SOURCES = [
    {"name": "Good Judgment (Платформа superforecasting)", "url": "https://goodjudgment.com/feed/"},
    {"name": "Johns Hopkins (Академический think-tank)", "url": "https://www.centerforhealthsecurity.org/feed.xml"},
    {"name": "Metaculus (Онлайн-платформа)", "url": "https://www.metaculus.com/feed/"},
    {"name": "DNI Global Trends (Гос. think-tank)", "url": "https://www.dni.gov/index.php/gt2040-home?format=feed&type=rss"},
    {"name": "RAND Corporation (Think-tank)", "url": "https://www.rand.org/rss.xml"},
    {"name": "World Economic Forum (Think-tank/форум)", "url": "https://www.weforum.org/rss"},
    {"name": "CSIS (Think-tank)", "url": "https://www.csis.org/rss.xml"},
    {"name": "Atlantic Council (Think-tank)", "url": "https://www.atlanticcouncil.org/feed/"},
    {"name": "Chatham House (Think-tank)", "url": "https://www.chathamhouse.org/feeds/all"},
    {"name": "The Economist (Журнал)", "url": "https://www.economist.com/rss/rss.xml"},
    {"name": "Bloomberg (Онлайн/broadcaster)", "url": "https://www.bloomberg.com/politics/feeds/site.xml"},
    {"name": "Reuters Institute (Академический/онлайн)", "url": "https://reutersinstitute.politics.ox.ac.uk/rss.xml"},
    {"name": "Foreign Affairs (Журнал)", "url": "https://www.foreignaffairs.com/rss.xml"},
    {"name": "CFR (Think-tank)", "url": "https://www.cfr.org/rss/"},
    {"name": "BBC Future (Broadcaster/онлайн)", "url": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml"},
    {"name": "Future Timeline (Нишевый блог)", "url": "https://www.futuretimeline.net/feed/"},
    {"name": "Carnegie Endowment (Think-tank)", "url": "https://carnegieendowment.org/rss.xml"},
    {"name": "Bruegel (Think-tank)", "url": "https://www.bruegel.org/rss.xml"},
    {"name": "E3G (Think-tank)", "url": "https://www.e3g.org/feed/"},
]

# Ключевые слова для фильтрации
KEYWORDS = [
    r"\brussia\b", r"\brussian\b", r"\bputin\b", r"\bmoscow\b", r"\bkremlin\b", r"\bukraine\b", r"\bukrainian\b",
    r"\bzelensky\b", r"\bkyiv\b", r"\bkiev\b", r"\bcrimea\b", r"\bdonbas\b", r"\bsanction[s]?\b", r"\bgazprom\b",
    r"\bnord\s?stream\b", r"\bwagner\b", r"\blavrov\b", r"\bshoigu\b", r"\bnato\b", r"\bwar\b", r"\bвойна\b",
    r"\bbitcoin\b", r"\bbtc\b", r"\bбиткоин\b", r"\bсанкции\b", r"\bцифровой рубль\b", r"\bpandemic\b", r"\bвирус\b",
    r"\bвакцина\b", r"\bvaccine\b", r"\blockdown\b", r"\bлокдаун\b", r"\bmutation\b", r"\bмутация\b", r"\bomicron\b",
    r"\bdrone\b", r"\bдрон\b", r"\bmissile\b", r"\bракета\b", r"\bhour ago\b", r"\bчас назад\b", r"\b刚刚\b",
    r"\bsec\b", r"\bцб рф\b", r"\bрегуляция\b", r"\bban\b", r"\bзапрет\b", r"\bdefi\b", r"\bnft\b", r"\bcbdc\b"
]

DB_PATH = "seen_titles.db"
INTERVAL_SEC = 180
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
            CREATE TABLE IF NOT EXISTS seen_titles (
                title_hash TEXT PRIMARY KEY,
                processed_at TEXT NOT NULL
            )
        """)
        conn.commit()

def normalize_title(title: str) -> str:
    return re.sub(r"[^a-zA-Zа-яА-Я0-9ёЁ]", "", title.lower()).strip()

def is_title_seen(title: str) -> bool:
    norm = normalize_title(title)
    if not norm:
        return False
    h = hashlib.sha256(norm.encode("utf-8")).hexdigest()
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("SELECT 1 FROM seen_titles WHERE title_hash = ?", (h,))
        return cur.fetchone() is not None

def mark_title_seen(title: str):
    norm = normalize_title(title)
    if not norm:
        return
    h = hashlib.sha256(norm.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO seen_titles (title_hash, processed_at) VALUES (?, ?)",
            (h, now)
        )
        conn.execute(f"""
            DELETE FROM seen_titles
            WHERE title_hash NOT IN (
                SELECT title_hash FROM seen_titles
                ORDER BY processed_at DESC
                LIMIT {MAX_DB_SIZE}
            )
        """)
        conn.commit()

# ============= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =============
def clean_text(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()

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
            return text

def escape_md(text: str) -> str:
    for c in r'\_[]()~`>#+-=|{}.!':
        text = text.replace(c, '\\' + c)
    return text

# ============= ПОЛУЧЕНИЕ НОВОСТЕЙ =============
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

                if is_title_seen(title):
                    continue

                if not any(re.search(kw, title, re.IGNORECASE) for kw in KEYWORDS):
                    continue

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

                safe_title = escape_md(ru_title)
                safe_desc = escape_md(ru_desc)
                source_bold = f"*{src['name']}*"  # Жирный источник

                msg = f"{source_bold}\n\n{safe_title}\n\n{safe_desc}\n\n[Источник]({link})"
                items.append((msg, title))
        except Exception as e:
            log.error(f"Ошибка при обработке {src['name']}: {e}")
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
        return r.status_code == 200
    except Exception as e:
        log.error(f"Ошибка отправки в Telegram: {e}")
        return False

# ============= HEALTH CHECK =============
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        pass

def start_health_server():
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
            for msg, orig_title in news:
                if send_to_telegram(msg):
                    mark_title_seen(orig_title)
                    sent += 1
                time.sleep(1)
            log.info(f"✅ Цикл завершён. Отправлено: {sent}")
        except Exception as e:
            log.exception(f"Критическая ошибка в основном цикле: {e}")
        time.sleep(INTERVAL_SEC)

# ============= ЗАПУСК =============
if __name__ == "__main__":
    threading.Thread(target=start_health_server, daemon=True).start()
    log.info(f"🚀 Бот запущен. Канал: {CHANNEL_ID}")
    main_loop()

