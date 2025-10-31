import os
import re
import time
import logging
import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator, MyMemoryTranslator
import schedule
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# ================== НАСТРОЙКИ ==================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@time_n_John")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан")

# Источники: только с рабочими RSS (Carnegie удалён — 404)
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
    {"name": "The Economist", "url": "https://www.economist.com/latest/rss.xml"},
    {"name": "Bloomberg Politics", "url": "https://www.bloomberg.com/politics/feeds/site.xml"},
]

# 🔍 Расширенные ключевые слова по теме "Россия и всё, что с ней связано"
KEYWORDS = [
    # Россия и синонимы
    r"\brussia\b", r"\brussian\b", r"\brussians\b", r"\brus\b",
    # Лидеры и чиновники
    r"\bputin\b", r"\bvladimir putin\b", r"\bmedvedev\b", r"\blavrov\b",
    r"\bshoigu\b", r"\bpeskov\b", r"\bpatrushev\b", r"\bnaryshkin\b",
    # Военные и структуры
    r"\bwagner\b", r"\bprigozhin\b", r"\bgazprom\b", r"\brosgaz\b",
    # География РФ
    r"\bmoscow\b", r"\bst petersburg\b", r"\bkrasnoyarsk\b", r"\bchechnya\b",
    r"\bdagestan\b", r"\bkaliningrad\b", r"\bcrimea\b", r"\bsevastopol\b",
    # Украина и регионы
    r"\bukraine\b", r"\bukrainian\b", r"\bkyiv\b", r"\bkiev\b", r"\bkharkiv\b",
    r"\bodesa\b", r"\bodessa\b", r"\bdonbas\b", r"\bdonetsk\b", r"\bluhansk\b",
    r"\bzelensky\b", r"\bvolodymyr zelensky\b",
    # Санкции и экономика
    r"\bsanction[s]?\b", r"\bembargo\b", r"\brestrict\b", r"\bruble\b", r"\brub\b",
    r"\beconomy\b", r"\boil\b", r"\bgas\b", r"\bnord\s?stream\b", r"\byamal\b",
    r"\bswift\b", r"\bimf\b", r"\bworld bank\b",
    # Военные действия
    r"\bwar\b", r"\bconflict\b", r"\bmilitary\b", r"\barmy\b", r"\battack\b",
    r"\bstrike\b", r"\binvasion\b", r"\bdrone\b", r"\bmissile\b", r"\bnuclear\b",
    # Международная реакция
    r"\bnato\b", r"\beuropa\b", r"\beuropean union\b", r"\bgermany\b", r"\bfrance\b",
    r"\busa\b", r"\bunited states\b", r"\buk\b", r"\bbritain\b", r"\bpoland\b",
    r"\bestonia\b", r"\blatvia\b", r"\blithuania\b", r"\bfinland\b", r"\bsweden\b",
    # Дипломатия и история
    r"\bdiplomat\b", r"\btalks\b", r"\bnegotiat\b", r"\bkremlin\b",
    r"\bsoviet\b", r"\bussr\b", r"\bpost\W?soviet\b", r"\bcommunist\b"
]

MAX_SEEN = 5000
MAX_PER_RUN = 12
seen_links = set()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

def clean_text(t):
    return re.sub(r"\s+", " ", t).strip()

def translate_to_russian(text):
    try:
        return GoogleTranslator(source='auto', target='ru').translate(text)
    except Exception as e1:
        log.warning(f"Google Translate failed: {e1}")
        try:
            return MyMemoryTranslator(source='en', target='ru').translate(text)
        except Exception as e2:
            log.warning(f"MyMemoryTranslator failed: {e2}")
            return text

def get_source_prefix(name):
    name = name.lower()
    mapping = {
        "e3g": "e3g",
        "foreign affairs": "foreignaffairs",
        "chatham house": "chathamhouse",
        "csis": "csis",
        "atlantic council": "atlanticcouncil",
        "rand": "rand",
        "cfr": "cfr",
        "bruegel": "bruegel",
        "bloomberg": "bloomberg",
        "reuters institute": "reuters",
        "the economist": "economist"
    }
    for key, val in mapping.items():
        if key in name:
            return val
    return name.split()[0].lower()

def fetch_rss_news():
    global seen_links
    result = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    for src in SOURCES:
        if len(result) >= MAX_PER_RUN:
            break
        try:
            url = src["url"]  # без strip(), так как пробелы убраны в SOURCES
            log.info(f"📡 {src['name']}")
            resp = requests.get(url, timeout=20, headers=headers)
            soup = BeautifulSoup(resp.content, "xml")

            for item in soup.find_all("item"):
                if len(result) >= MAX_PER_RUN:
                    break

                title = clean_text(item.title.get_text()) if item.title else ""
                link = (item.link.get_text() or item.guid.get_text()).strip() if item.link or item.guid else ""

                if not title or not link or link in seen_links:
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

                msg = f"{prefix}: {safe_title}\n\n{safe_lead}\n\n[Источник]({link})"
                result.append({"msg": msg, "link": link})

        except Exception as e:
            log.error(f"❌ {src['name']}: {e}")

    return result

def send_to_telegram(text):
    # 🔥 ИСПРАВЛЕНО: убраны пробелы в URL
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

def job_main():
    global seen_links
    log.info("🔄 Основная проверка новостей...")
    news = fetch_rss_news()
    if not news:
        log.info("📭 Нет релевантных публикаций.")
        return

    for item in news:
        send_to_telegram(item["msg"])
        seen_links.add(item["link"])
        if len(seen_links) > MAX_SEEN:
            seen_links = set(list(seen_links)[-4000:])
        time.sleep(2)

def job_keepalive():
    """Фоновая проверка каждые 10 минут — чтобы Render не уснул"""
    log.info("💤 Keep-alive check (фон)")

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

    threading.Thread(target=start_server, daemon=True).start()

    log.info("🚀 Бот запущен. Основная проверка каждые 30 мин + keep-alive каждые 10 мин.")

    # Первый запуск сразу
    job_main()

    # Основная задача — каждые 30 минут
    schedule.every(30).minutes.do(job_main)
    # Keep-alive — каждые 10 минут (чтобы Render Free не уснул)
    schedule.every(10).minutes.do(job_keepalive)

    while True:
        schedule.run_pending()
        time.sleep(1)
