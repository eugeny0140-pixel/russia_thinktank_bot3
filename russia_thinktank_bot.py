# russia_thinktank_bot.py
import os
import re
import time
import logging
import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
import schedule
import psycopg2
from psycopg2.extras import RealDictCursor

# ================== НАСТРОЙКИ ==================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")  # УБРАЛИ дефолтные значения!
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан")
if not CHANNEL_ID:
    raise ValueError("CHANNEL_ID не задан — укажите в переменных окружения")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL не задан — необходим для отслеживания уже отправленных ссылок")

# Инициализация БД
def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS seen_links (
                link TEXT PRIMARY KEY,
                seen_at TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.commit()
    conn.close()
    log.info("✅ База данных инициализирована")

def is_link_seen(link):
    conn = psycopg2.connect(DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM seen_links WHERE link = %s", (link,))
        result = cur.fetchone()
    conn.close()
    return result is not None

def mark_link_as_seen(link):
    conn = psycopg2.connect(DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO seen_links (link) VALUES (%s) ON CONFLICT DO NOTHING", (link,))
        conn.commit()
    conn.close()

# ================== ОСТАЛЬНОЙ КОД ==================
SOURCES = [
    {"name": "E3G", "url": "https://www.e3g.org/feed/"},
    {"name": "Foreign Affairs", "url": "https://www.foreignaffairs.com/rss.xml"},
    {"name": "Reuters Institute", "url": "https://reutersinstitute.politics.ox.ac.uk/rss.xml"},
    {"name": "Bruegel", "url": "https://www.bruegel.org/rss.xml"},
    {"name": "Chatham House", "url": "https://www.chathamhouse.org/rss.xml"},
    {"name": "CSIS", "url": "https://www.csis.org/rss.xml"},
    {"name": "Atlantic Council", "url": "https://www.atlanticcouncil.org/feed/"},
    {"name": "RAND Corporation", "url": "https://www.rand.org/rss.xml"},
    {"name": "CFR", "url": "https://www.cfr.org/rss/"},
    {"name": "Carnegie Endowment", "url": "https://carnegieendowment.org/rss.xml"},
    {"name": "The Economist", "url": "https://www.economist.com/latest/rss.xml"},
    {"name": "Bloomberg Politics", "url": "https://www.bloomberg.com/politics/feeds/site.xml"},
    {"name": "Chatham House – Russia", "url": "https://www.chathamhouse.org/topics/russia/rss.xml"},
    {"name": "Chatham House – Europe", "url": "https://www.chathamhouse.org/topics/europe/rss.xml"},
    {"name": "Chatham House – International Security", "url": "https://www.chathamhouse.org/topics/international-security/rss.xml"},
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
    r"\binfection rate\b", r"\bзаразность\b", r"\b死亡率\b", r"\bhospitalization\b", r"\bгоспитализация\b", r"\bقبل ساعات\b", r"\b刚刚报告\b"
]

MAX_PER_RUN = 12

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

def clean_text(t):
    return re.sub(r"\s+", " ", t).strip()

def translate_to_russian(text):
    try:
        return GoogleTranslator(source='auto', target='ru').translate(text)
    except Exception as e:
        log.error(f"❌ Ошибка перевода: {e}")
        return text

def get_source_prefix(name):
    name_lower = name.lower()
    mapping = {
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
    for key, val in mapping.items():
        if key in name_lower:
            return val
    return name.split()[0].lower()

def fetch_rss_news():
    result = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    for src in SOURCES:
        if len(result) >= MAX_PER_RUN:
            break
        try:
            url = src["url"].strip()
            log.info(f"📡 {src['name']}")
            resp = requests.get(url, timeout=30, headers=headers)
            soup = BeautifulSoup(resp.content, "xml")
            for item in soup.find_all("item"):
                if len(result) >= MAX_PER_RUN:
                    break
                title = clean_text(item.title.get_text()) if item.title else ""
                link = (item.link.get_text() or item.guid.get_text()).strip() if item.link or item.guid else ""
                if not title or not link or is_link_seen(link):  # Проверяем через БД!
                    continue
                if not any(re.search(kw, title, re.IGNORECASE) for kw in KEYWORDS):
                    continue
                lead = ""
                desc_tag = item.find("description") or item.find("content:encoded")
                if desc_tag:
                    raw_html = desc_tag.get_text()
                    desc_soup = BeautifulSoup(raw_html, "html.parser")
                    full_text = clean_text(desc_soup.get_text())
                    sentences = re.split(r'(?<=[.!?])\s+', full_text)
                    if sentences and sentences[0].strip():
                        lead = sentences[0].strip()
                    else:
                        lead = full_text[:250] + "…" if len(full_text) > 250 else full_text
                if not lead.strip():
                    continue
                ru_title = translate_to_russian(title)
                ru_lead = translate_to_russian(lead)
                def escape_md_v2(text):
                    for c in r'_*[]()~`>#+-=|{}.!':
                        text = text.replace(c, '\\' + c)
                    return text
                safe_title = escape_md_v2(ru_title)
                safe_lead = escape_md_v2(ru_lead)
                prefix = get_source_prefix(src["name"])
                msg = f"{prefix}: {safe_title}\n{safe_lead}\n[Источник]({link})"
                result.append({"msg": msg, "link": link})
        except Exception as e:
            log.error(f"❌ {src['name']}: {e}")
    return result

def send_to_telegram(text):
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
            log.info("✅ Отправлено")
        else:
            log.error(f"❌ Telegram error: {r.text}")
    except Exception as e:
        log.error(f"❌ Исключение: {e}")

def job():
    log.info("🔄 Проверка новостей...")
    news = fetch_rss_news()
    if not news:
        log.info("📭 Нет релевантных публикаций.")
        return
    for item in news:
        send_to_telegram(item["msg"])
        mark_link_as_seen(item["link"])  # Сохраняем в БД!
        time.sleep(1)

# ================== ЗАПУСК С HTTP-СЕРВЕРОМ ДЛЯ RENDER ==================
if __name__ == "__main__":
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import threading

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

    # Инициализация БД при старте
    init_db()

    threading.Thread(target=start_server, daemon=True).start()
    log.info("🚀 Бот запущен как Web Service на Render")

    job()
    schedule.every(3).minutes.do(job)

    while True:
        schedule.run_pending()
        time.sleep(1)
