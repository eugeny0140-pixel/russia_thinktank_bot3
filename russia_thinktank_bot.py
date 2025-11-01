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
    # 1. СВО и Война
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
r"\bhour ago\b", r"\bчас назад\b", r"\bminutos atrás\b", r"\b小时前\b"

# 2. Криптовалюта (топ-20 + CBDC, DeFi, регуляция)
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
r"\bhour ago\b", r"\bчас назад\b", r"\b刚刚\b", r"\bدقائق مضت\b"

# 3. Пандемия и болезни (включая биобезопасность)
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
r"\bhour ago\b", r"\bчас назад\b", r"\bقبل ساعات\b", r"\b刚刚报告\b"
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

