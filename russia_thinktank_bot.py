import os
import re
import time
import logging
import requests
import html
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator, MyMemoryTranslator
from http.server import HTTPServer, BaseHTTPRequestHandler
import psycopg2
import hashlib
import threading

# --- Настройки ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
CHANNEL_IDS = ["@time_n_John", "@finanosint"]

# Исправленные URL (убраны пробелы, исправлен RAND)
SOURCES = [
    {"name": "E3G", "url": "https://www.e3g.org/feed/"},
    {"name": "Foreign Affairs", "url": "https://www.foreignaffairs.com/rss.xml"},
    {"name": "Reuters Institute", "url": "https://reutersinstitute.politics.ox.ac.uk/rss.xml"},
    {"name": "Bruegel", "url": "https://www.bruegel.org/rss.xml"},
    {"name": "Chatham House – Russia", "url": "https://www.chathamhouse.org/topics/russia/rss.xml"},
    {"name": "Chatham House – Europe", "url": "https://www.chathamhouse.org/topics/europe/rss.xml"},
    {"name": "Chatham House – International Security", "url": "https://www.chathamhouse.org/topics/international-security/rss.xml"},
    {"name": "CSIS", "url": "https://www.csis.org/rss.xml"},
    {"name": "Atlantic Council", "url": "https://www.atlanticcouncil.org/feed/"},
    {"name": "RAND Corporation", "url": "https://www.rand.org/rss.xml"},  # Исправлено
    {"name": "CFR", "url": "https://www.cfr.org/rss/"},
    {"name": "The Economist", "url": "https://www.economist.com/latest/rss.xml"},
    {"name": "Bloomberg Politics", "url": "https://www.bloomberg.com/politics/feeds/site.xml"},
    {"name": "Carnegie Endowment", "url": "https://carnegieendowment.org/rss.xml"},
    {"name": "BBC Future Planet", "url": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml"},
]

KEYWORDS = [
    r"\brussia\b", r"\brussian\b", r"\bputin\b", r"\bmoscow\b", r"\bkremlin\b",
    r"\bukraine\b", r"\bukrainian\b", r"\bzelensky\b", r"\bkyiv\b", r"\bkiev\b",
    r"\bcrimea\b", r"\bdonbas\b", r"\bsanction[s]?\b", r"\bgazprom\b",
    r"\bnord\s?stream\b", r"\bwagner\b", r"\blavrov\b", r"\bshoigu\b",
    r"\bmedvedev\b", r"\bpeskov\b", r"\bnato\b", r"\beuropa\b", r"\busa\b",
    r"\bsoviet\b", r"\bussr\b", r"\bpost\W?soviet\b",
    r"\bsvo\b", r"\bспецоперация\b", r"\bspecial military operation\b",
    r"\bвойна\b", r"\bwar\b", r"\bconflict\b", r"\bконфликт\b",
    r"\bнаступление\b", r"\boffensive\b", r"\bатака\b", r"\battack\b",
    r"\bудар\b", r"\bstrike\b", r"\bобстрел\b", r"\bshelling\b",
    r"\bдрон\b", r"\bdrone\b", r"\bmissile\b", r"\bракета\b",
    r"\bэскалация\b", r"\bescalation\b", r"\bмобилизация\b", r"\bmobilization\b",
    r"\bфронт\b", r"\bfrontline\b", r"\bзахват\b", r"\bcapture\b",
    r"\bосвобождение\b", r"\bliberation\b", r"\bбой\b", r"\bbattle\b",
    r"\bпотери\b", r"\bcasualties\b", r"\bпогиб\b", r"\bkilled\b",
    r"\bранен\b", r"\binjured\b", r"\bпленный\b", r"\bprisoner of war\b",
    r"\bпереговоры\b", r"\btalks\b", r"\bперемирие\b", r"\bceasefire\b",
    r"\bсанкции\b", r"\bsanctions\b", r"\bоружие\b", r"\bweapons\b",
    r"\bпоставки\b", r"\bsupplies\b", r"\bhimars\b", r"\batacms\b",
    r"\bhour ago\b", r"\bчас назад\b", r"\bminutos atrás\b", r"\b小时前\b",
    r"\bbitcoin\b", r"\bbtc\b", r"\bбиткоин\b", r"\b比特币\b",
    r"\bethereum\b", r"\beth\b", r"\bэфир\b", r"\b以太坊\b",
    r"\bbinance coin\b", r"\bbnb\b", r"\busdt\b", r"\btether\b",
    r"\bxrp\b", r"\bripple\b", r"\bcardano\b", r"\bada\b",
    r"\bsolana\b", r"\bsol\b", r"\bdoge\b", r"\bdogecoin\b",
    r"\bavalanche\b", r"\bavax\b", r"\bpolkadot\b", r"\bdot\b",
    r"\bchainlink\b", r"\blink\b", r"\btron\b", r"\btrx\b",
    r"\bcbdc\b", r"\bcentral bank digital currency\b", r"\bцифровой рубль\b",
    r"\bdigital yuan\b", r"\beuro digital\b", r"\bdefi\b", r"\bдецентрализованные финансы\b",
    r"\bnft\b", r"\bnon-fungible token\b", r"\bsec\b", r"\bцб рф\b",
    r"\bрегуляция\b", r"\bregulation\b", r"\bзапрет\b", r"\bban\b",
    r"\bмайнинг\b", r"\bmining\b", r"\bhalving\b", r"\bхалвинг\b",
    r"\bволатильность\b", r"\bvolatility\b", r"\bcrash\b", r"\bкрах\b",
    r"\b刚刚\b", r"\bدقائق مضت\b",
    r"\bpandemic\b", r"\bпандемия\b", r"\b疫情\b", r"\bجائحة\b",
    r"\boutbreak\b", r"\bвспышка\b", r"\bэпидемия\b", r"\bepidemic\b",
    r"\bvirus\b", r"\bвирус\b", r"\bвирусы\b", r"\b变异株\b",
    r"\bvaccine\b", r"\bвакцина\b", r"\b疫苗\b", r"\bلقاح\b",
    r"\bbooster\b", r"\bбустер\b", r"\bревакцинация\b",
    r"\bquarantine\b", r"\bкарантин\b", r"\b隔离\b", r"\bحجر صحي\b",
    r"\blockdown\b", r"\bлокдаун\b", r"\b封锁\b",
    r"\bmutation\b", r"\bмутация\b", r"\b变异\b",
    r"\bstrain\b", r"\bштамм\b", r"\bomicron\b", r"\bdelta\b",
    r"\bbiosafety\b", r"\bбиобезопасность\b", r"\b生物安全\b",
    r"\blab leak\b", r"\bлабораторная утечка\b", r"\b实验室泄漏\b",
    r"\bgain of function\b", r"\bусиление функции\b",
    r"\bwho\b", r"\bвоз\b", r"\bcdc\b", r"\bроспотребнадзор\b",
    r"\binfection rate\b", r"\bзаразность\b", r"\b死亡率\b",
    r"\bhospitalization\b", r"\bгоспитализация\b",
    r"\bقبل ساعات\b", r"\b刚刚报告\b"
]

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger()

# Интервал между проверками (в секундах). Для "реального времени" — 10–15 сек.
FETCH_INTERVAL = 14

# --- Функции работы с БД ---
def get_db_conn():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def is_seen(link):
    h = hashlib.sha256(link.encode()).hexdigest()
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM seen_links WHERE link_hash = %s", (h,))
            return cur.fetchone() is not None

def mark_seen(link):
    h = hashlib.sha256(link.encode()).hexdigest()
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO seen_links (link_hash) VALUES (%s)
                ON CONFLICT (link_hash) DO NOTHING
            """, (h,))
        conn.commit()

# --- Перевод ---
def translate(text):
    if not text or not text.strip():
        return text
    clean_text = text.strip()
    try:
        return GoogleTranslator(source='auto', target='ru').translate(clean_text)
    except Exception as e1:
        log.debug(f"GoogleTranslator failed: {e1}")
        try:
            return MyMemoryTranslator(source='auto', target='ru').translate(clean_text)
        except Exception as e2:
            log.debug(f"MyMemoryTranslator failed: {e2}")
            return clean_text

# --- Префикс источника ---
def get_prefix(name):
    name_lower = name.lower()
    prefixes = {
        "e3g": "E3G",
        "foreign affairs": "FOREIGNAFFAIRS",
        "reuters": "REUTERS",
        "bruegel": "BRUEGEL",
        "chatham house": "CHATHAM_RU" if "russia" in name_lower else ("CHATHAM_EU" if "europe" in name_lower else "CHATHAM"),
        "csis": "CSIS",
        "atlantic": "ATLANTICCOUNCIL",
        "rand": "RAND",
        "cfr": "CFR",
        "economist": "ECONOMIST",
        "bloomberg": "BLOOMBERG",
        "carnegie": "CARNEGIE",
        "bbc": "BBC"
    }
    for key, prefix in prefixes.items():
        if key in name_lower:
            return prefix
    return name.split()[0].upper()

# --- Основная логика ---
def fetch_news():
    headers = {"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"}
    messages = []
    for src in SOURCES:
        try:
            url = src["url"]
            resp = requests.get(url, timeout=20, headers=headers)
            if resp.status_code != 200:
                log.warning(f"{src['name']}: HTTP {resp.status_code}")
                continue

            soup = BeautifulSoup(resp.content, "xml")
            items = soup.find_all("item")
            if not items:
                log.debug(f"{src['name']}: no <item> found")
                continue

            for item in items:
                link_tag = item.find("link")
                link = link_tag.get_text().strip() if link_tag else ""
                if not link:
                    continue
                # Сохраняем полную ссылку для уникальности (без обрезки параметров)
                canonical_link = link.split('#')[0]  # убираем якоря, но оставляем параметры

                if is_seen(canonical_link):
                    continue

                title_tag = item.find("title")
                title = html.unescape(title_tag.get_text().strip()) if title_tag else ""
                if not title:
                    continue

                desc_tag = item.find("description")
                desc_raw = desc_tag.get_text() if desc_tag else ""
                desc_soup = BeautifulSoup(desc_raw, "html.parser")
                desc_text = desc_soup.get_text().strip()
                desc = re.split(r'(?<=[.!?])\s+', desc_text)[0] if desc_text else desc_text[:200]

                # Проверяем ключевые слова в заголовке И описании
                full_text = f"{title} {desc}"
                if not any(re.search(kw, full_text, re.IGNORECASE) for kw in KEYWORDS):
                    continue

                if not desc.strip():
                    desc = "Без описания."

                ru_title = translate(title).replace("\\", "")
                ru_desc = translate(desc).replace("\\", "")
                prefix = get_prefix(src["name"])
                msg = f"<b>{prefix}</b>: {ru_title}\n\n{ru_desc}\n\nИсточник: {canonical_link}"
                messages.append((msg, canonical_link))

        except Exception as e:
            log.error(f"{src['name']}: {e}")

    return messages

# --- Отправка в Telegram ---
def send_telegram(text):
    success = True
    for cid in CHANNEL_IDS:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"  # Исправлено: убраны пробелы
        data = {
            "chat_id": cid,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            r = requests.post(url, data=data, timeout=10)
            if r.status_code == 200:
                log.info(f"✅ Отправлено в {cid}")
            else:
                log.error(f"❌ Ошибка Telegram {cid}: {r.status_code} {r.text}")
                success = False
        except Exception as e:
            log.error(f"❌ Исключение при отправке в {cid}: {e}")
            success = False
    return success

# --- Health check для хостинга (например, Render) ---
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def start_server():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()

# --- Запуск ---
if __name__ == "__main__":
    # Создание таблицы
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS seen_links (
                    link_hash VARCHAR(64) PRIMARY KEY,
                    processed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
        conn.commit()

    # Запуск health-check сервера в фоне
    threading.Thread(target=start_server, daemon=True).start()
    log.info("🚀 Бот запущен. Health-check на порту $PORT")

    while True:
        try:
            news_items = fetch_news()
            for msg, link in news_items:
                # Сначала помечаем как обработанное — чтобы избежать дубликатов при сбое
                mark_seen(link)
                if not send_telegram(msg):
                    log.warning(f"Сообщение отправлено в БД, но не в Telegram: {link}")
                time.sleep(1)  # пауза между отправками
            log.info(f"✅ Цикл завершён. Найдено: {len(news_items)} новых новостей.")
        except Exception as e:
            log.exception(f"Критическая ошибка в основном цикле: {e}")

        time.sleep(FETCH_INTERVAL)
