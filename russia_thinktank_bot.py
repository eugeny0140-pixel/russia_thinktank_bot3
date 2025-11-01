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

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@time_n_John")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан")

# Источники с рабочими RSS (Carnegie удалён — 404)
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

# 🔍 Расширенные ключевые слова
KEYWORDS = [
    # === Основные: Россия, Украина, геополитика ===
    r"\brussia\b", r"\brussian\b", r"\bputin\b", r"\bmoscow\b", r"\bkremlin\b",
    r"\bukraine\b", r"\bukrainian\b", r"\bzelensky\b", r"\bkyiv\b", r"\bkiev\b",
    r"\bcrimea\b", r"\bdonbas\b", r"\bsanction[s]?\b", r"\bgazprom\b",
    r"\bnord\s?stream\b", r"\bwagner\b", r"\blavrov\b", r"\bshoigu\b",
    r"\bmedvedev\b", r"\bpeskov\b", r"\bnato\b", r"\beuropa\b", r"\busa\b",
    r"\bsoviet\b", r"\bussr\b", r"\bpost\W?soviet\b",

    # === 1. СВО и Война ===
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
    r"\bоружие\b", r"\bweapons\b", r"\bпоставки\b", r"\bsupplies\b", 
    r"\bhimars\b", r"\batacms\b",

    # === 2. Криптовалюта ===
    r"\bbitcoin\b", r"\bbtc\b", r"\bбиткоин\b", 
    r"\bethereum\b", r"\beth\b", r"\bэфир\b", 
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

    # === 3. Пандемия и биобезопасность ===
    r"\bpandemic\b", r"\bпандемия\b", r"\boutbreak\b", r"\bвспышка\b", 
    r"\bvirus\b", r"\bвирус\b", r"\bvaccine\b", r"\bвакцина\b", 
    r"\bbooster\b", r"\bбустер\b", r"\bquarantine\b", r"\bкарантин\b", 
    r"\blockdown\b", r"\bлокдаун\b", r"\bmutation\b", r"\bмутация\b", 
    r"\bstrain\b", r"\bштамм\b", r"\bomicron\b", r"\bdelta\b", 
    r"\bbiosafety\b", r"\bбиобезопасность\b", r"\blab leak\b", r"\bлабораторная утечка\b", 
    r"\bgain of function\b", r"\bусиление функции\b", r"\bwho\b", r"\bвоз\b", 
    r"\binfection rate\b", r"\bзаразность\b", r"\bhospitalization\b", r"\bгоспитализация\b",
]

seen_links = set()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger()

def translate(text):
    try:
        return GoogleTranslator(source='auto', target='ru').translate(text)
    except Exception as e1:
        log.warning(f"Google Translate failed: {e1}")
        try:
            return MyMemoryTranslator(source='en', target='ru').translate(text)
        except Exception as e2:
            log.warning(f"MyMemoryTranslator failed: {e2}")
            return text

def get_prefix(name):
    name = name.lower()
    if "e3g" in name: return "e3g"
    if "foreign affairs" in name: return "foreignaffairs"
    if "reuters" in name: return "reuters"
    if "bruegel" in name: return "bruegel"
    if "chatham" in name: return "chathamhouse"
    if "csis" in name: return "csis"
    if "atlantic" in name: return "atlanticcouncil"
    if "rand" in name: return "rand"
    if "cfr" in name: return "cfr"
    if "economist" in name: return "economist"
    if "bloomberg" in name: return "bloomberg"
    return name.split()[0].lower()

def fetch_one_per_source():
    headers = {"User-Agent": "Mozilla/5.0"}
    messages = []
    for src in SOURCES:
        try:
            resp = requests.get(src["url"], timeout=20, headers=headers)
            soup = BeautifulSoup(resp.content, "xml")
            item = soup.find("item")
            if not item:
                continue

            link = (item.link and item.link.get_text().strip()) or ""
            title = (item.title and item.title.get_text().strip()) or ""
            if not title or not link or link in seen_links:
                continue

            if not any(re.search(kw, title, re.IGNORECASE) for kw in KEYWORDS):
                continue

            desc = ""
            desc_tag = item.find("description")
            if desc_tag:
                raw = BeautifulSoup(desc_tag.get_text(), "html.parser").get_text()
                sentences = re.split(r'(?<=[.!?])\s+', raw.strip())
                desc = sentences[0] if sentences else raw[:200]

            if not desc.strip():
                continue

            ru_title = translate(title)
            ru_desc = translate(desc)
            prefix = get_prefix(src["name"]).upper()  # ВЕРХНИЙ РЕГИСТР

            # Формат с HTML: <b>BLOOMBERG</b>: ...
            msg = f"<b>**{prefix}**</b>: {ru_title}\n\n{ru_desc}\n\nИсточник: {link}"
            messages.append((msg, link))

        except Exception as e:
            log.error(f"Ошибка {src['name']}: {e}")
    return messages

def job_main():
    log.info("🔄 Проверка новостей...")
    messages = fetch_one_per_source()
    count = 0
    for msg, link in messages:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id": CHANNEL_ID,
            "text": msg,
            "parse_mode": "HTML",  # ← КЛЮЧЕВОЕ: HTML для жирного шрифта
            "disable_web_page_preview": True,
        }
        try:
            r = requests.post(url, data=data, timeout=10)
            log.info("✅ Отправлено" if r.status_code == 200 else f"❌ Ошибка: {r.text}")
        except Exception as e:
            log.error(f"❌ Исключение: {e}")

        seen_links.add(link)
        count += 1
        time.sleep(2)
    log.info(f"✅ Проверка завершена. Отправлено: {count}")

def job_keepalive():
    log.info("💤 Keep-alive check")

# === HTTP-сервер для Render ===
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
    log.info("🚀 Бот запущен. Основная проверка каждые 30 мин.")

    job_main()
    schedule.every(1).minutes.do(job_main)
  

    while True:
        schedule.run_pending()
        time.sleep(1)
