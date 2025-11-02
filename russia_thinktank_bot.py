import os
import re
import time
import logging
import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator, MyMemoryTranslator
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@time_n_John")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан")

# ✅ Исправленные источники: без пробелов, только рабочие RSS
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
    {"name": "RAND Corporation", "url": "https://www.rand.org/rss.xml"},
    # ❌ CFR отключён — официального RSS нет, возвращает 404
    # {"name": "CFR", "url": "https://www.cfr.org/rss/"},
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

seen_links = set()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger()

# Полные заголовки для имитации браузера
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

def translate(text):
    if not text or not text.strip():
        return text
    try:
        return GoogleTranslator(source='auto', target='ru').translate(text)
    except Exception as e1:
        log.warning(f"GoogleTranslator failed: {e1}")
        try:
            return MyMemoryTranslator(source='auto', target='ru').translate(text)
        except Exception as e2:
            log.warning(f"MyMemoryTranslator failed: {e2}")
            return text

def get_prefix(name):
    name = name.lower()
    if "e3g" in name: return "E3G"
    if "foreign affairs" in name: return "FOREIGNAFFAIRS"
    if "reuters" in name: return "REUTERS"
    if "bruegel" in name: return "BRUEGEL"
    if "chatham house" in name:
        if "russia" in name: return "CHATHAM_RU"
        if "europe" in name: return "CHATHAM_EU"
        if "security" in name: return "CHATHAM_SEC"
        return "CHATHAM"
    if "csis" in name: return "CSIS"
    if "atlantic" in name: return "ATLANTICCOUNCIL"
    if "rand" in name: return "RAND"
    if "cfr" in name: return "CFR"
    if "economist" in name: return "ECONOMIST"
    if "bloomberg" in name: return "BLOOMBERG"
    if "carnegie" in name: return "CARNEGIE"
    if "bbc" in name: return "BBC"
    return name.split()[0].upper()

def fetch_one_per_source():
    session = requests.Session()
    session.headers.update(HEADERS)
    messages = []
    for src in SOURCES:
        try:
            log.info(f"Проверка: {src['name']}")
            resp = session.get(src["url"], timeout=20)
            if resp.status_code != 200:
                log.warning(f"HTTP {resp.status_code} from {src['name']}")
                time.sleep(1)
                continue

            soup = BeautifulSoup(resp.content, "xml")
            item = soup.find("item")
            if not item:
                time.sleep(1)
                continue

            link = (item.link and item.link.get_text().strip()) or ""
            if not link:
                time.sleep(1)
                continue
            link = link.split('?')[0].rstrip('/')

            if link in seen_links:
                time.sleep(1)
                continue

            title = (item.title and item.title.get_text().strip()) or ""
            if not title:
                time.sleep(1)
                continue

            if not any(re.search(kw, title, re.IGNORECASE) for kw in KEYWORDS):
                time.sleep(1)
                continue

            desc = ""
            desc_tag = item.find("description")
            if desc_tag:
                raw = BeautifulSoup(desc_tag.get_text(), "html.parser").get_text()
                sentences = re.split(r'(?<=[.!?])\s+', raw.strip())
                desc = sentences[0] if sentences else raw[:200]
            if not desc.strip():
                time.sleep(1)
                continue

            ru_title = translate(title).replace("\\", "")
            ru_desc = translate(desc).replace("\\", "")
    
            prefix = get_prefix(src["name"])
            msg = f"<b>{prefix}</b>: {ru_title}\n\n{ru_desc}\n\nИсточник: {link}"
            messages.append((msg, link))
            time.sleep(1)  # Задержка между источниками

        except Exception as e:
            log.error(f"Ошибка {src['name']}: {e}")
            time.sleep(1)
    return messages

def send_to_telegram(text):
    # ✅ Исправлен URL: убраны пробелы!
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, data=data, timeout=10)
        if r.status_code == 200:
            log.info("✅ Отправлено")
            return True
        else:
            log.error(f"❌ Ошибка Telegram: {r.status_code} {r.text}")
            return False
    except Exception as e:
        log.error(f"❌ Исключение Telegram: {e}")
        return False

# === HTTP-сервер для Railway/Render ===
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args): pass

def start_server():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()

# === ЗАПУСК ===
if __name__ == "__main__":
    threading.Thread(target=start_server, daemon=True).start()
    log.info("🚀 Бот запущен. Проверка RSS каждые 14 минут.")

    while True:
        messages = fetch_one_per_source()
        count = 0
        for msg, link in messages:
            if send_to_telegram(msg):
                seen_links.add(link)
                count += 1
            time.sleep(2)  # Пауза между отправками
        log.info(f"✅ Цикл завершён. Новых новостей: {count}")
        time.sleep(14 * 60)  # 14 минут
