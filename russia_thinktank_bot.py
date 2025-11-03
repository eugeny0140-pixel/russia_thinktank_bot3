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
CHANNEL_ID = os.getenv("CHANNEL_ID", "@time_n_John")

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
   r"\brussia\b", r"\brussian\b", r"\bputin\b", r"\bmoscow\b", r"\bkremlin\b", r"\bukraine\b", r"\bukrainian\b", r"\bzelensky\b", r"\bkyiv\b", r"\bkiev\b", r"\bcrimea\b", r"\bdonbas\b", r"\bsanction[s]?\b", r"\bgazprom\b", r"\bnord\s?stream\b", r"\bwagner\b", r"\blavrov\b", r"\bshoigu\b", r"\bmedvedev\b", r"\bpeskov\b", r"\bnato\b", r"\beuropa\b", r"\busa\b", r"\bsoviet\b", r"\bussr\b", r"\bpost\W?soviet\b", r"\bsvo\b", r"\bспецоперация\b", r"\bspecial military operation\b", r"\bвойна\b", r"\bwar\b", r"\bconflict\b", r"\bконфликт\b", r"\bнаступление\b", r"\boffensive\b", r"\bатака\b", r"\battack\b", r"\bудар\b", r"\bstrike\b", r"\bобстрел\b", r"\bshelling\b", r"\bдрон\b", r"\bdrone\b", r"\bmissile\b", r"\bракета\b",  r"\bэскалация\b", r"\bescalation\b", r"\bмобилизация\b", r"\bmobilization\b", r"\bфронт\b", r"\bfrontline\b", r"\bзахват\b", r"\bcapture\b", r"\bосвобождение\b", r"\bliberation\b", r"\bбой\b", r"\bbattle\b", r"\bпотери\b", r"\bcasualties\b", r"\bпогиб\b", r"\bkilled\b", r"\bранен\b", r"\binjured\b", r"\bпленный\b", r"\bprisoner of war\b", r"\bпереговоры\b", r"\btalks\b", r"\bперемирие\b", r"\bceasefire\b", r"\bсанкции\b", r"\bsanctions\b", r"\bоружие\b", r"\bweapons\b", r"\bпоставки\b", r"\bsupplies\b", r"\bhimars\b", r"\batacms\b", r"\bhour ago\b", r"\bчас назад\b", r"\bminutos atrás\b", r"\b小时前\b", r"\bbitcoin\b", r"\bbtc\b", r"\bбиткоин\b", r"\b比特币\b", r"\bethereum\b", r"\beth\b", r"\bэфир\b", r"\b以太坊\b", r"\bbinance coin\b", r"\bbnb\b", r"\busdt\b", r"\btether\b", r"\bxrp\b", r"\bripple\b", r"\bcardano\b", r"\bada\b", r"\bsolana\b", r"\bsol\b", r"\bdoge\b", r"\bdogecoin\b", r"\bavalanche\b", r"\bavax\b", r"\bpolkadot\b", r"\bdot\b", r"\bchainlink\b", r"\blink\b", r"\btron\b", r"\btrx\b", r"\bcbdc\b", r"\bcentral bank digital currency\b", r"\bцифровой рубль\b", r"\bdigital yuan\b", r"\beuro digital\b", r"\bdefi\b", r"\bдецентрализованные финансы\b", r"\bnft\b", r"\bnon-fungible token\b", r"\bsec\b", r"\bцб рф\b", r"\bрегуляция\b", r"\bregulation\b", r"\bзапрет\b", r"\bban\b", r"\bмайнинг\b", r"\bmining\b", r"\bhalving\b", r"\bхалвинг\b", r"\bволатильность\b", r"\bvolatility\b", r"\bcrash\b", r"\bкрах\b", r"\b刚刚\b", r"\bدقائق مضت\b", r"\bpandemic\b", r"\bпандемия\b", r"\b疫情\b", r"\bجائحة\b", r"\boutbreak\b", r"\bвспышка\b", r"\bэпидемия\b", r"\bepidemic\b", r"\bvirus\b", r"\bвирус\b", r"\bвирусы\b", r"\b变异株\b",  r"\bvaccine\b", r"\bвакцина\b", r"\b疫苗\b", r"\bلقاح\b", r"\bbooster\b", r"\bбустер\b", r"\bревакцинация\b", r"\bquarantine\b", r"\bкарантин\b", r"\b隔离\b", r"\bحجر صحي\b", r"\blockdown\b", r"\bлокдаун\b", r"\b封锁\b", r"\bmutation\b", r"\bмутация\b", r"\b变异\b", r"\bstrain\b", r"\bштамм\b", r"\bomicron\b", r"\bdelta\b", r"\bbiosafety\b", r"\bбиобезопасность\b", r"\b生物安全\b", r"\blab leak\b", r"\bлабораторная утечка\b", r"\b实验室泄漏\b", r"\bgain of function\b", r"\bусиление функции\b", r"\bwho\b", r"\bвоз\b", r"\bcdc\b", r"\bроспотребнадзор\b", r"\binfection rate\b", r"\bзаразность\b", r"\b死亡率\b", r"\bhospitalization\b", r"\bгоспитализация\b", r"\bقبل ساعات\b", r"\b刚刚报告\b"]

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





