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

# Источники с рабочими RSS (без Carnegie — 404)
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

KEYWORDS = [
   # Россия и её синонимы
    r"\brussia\b", r"\brussian\b", r"\brussians\b", r"\brus\b", r"\brus'?sia\b",
    
    # Ключевые лица
    r"\bputin\b", r"\bvladimir putin\b", r"\bmedvedev\b", r"\bdmitry medvedev\b",
    r"\blavrov\b", r"\bsergey lavrov\b", r"\bshoigu\b", r"\bsergei shoigu\b",
    r"\bpeskov\b", r"\bdmitry peskov\b", r"\bnaryshkin\b", r"\bpatrushev\b",
    r"\bprigozhin\b", r"\bwagner\b", r"\bgazprom\b", r"\brosgaz\b",
    
    # География РФ и регионы
    r"\bmoscow\b", r"\bst petersburg\b", r"\bst\. petersburg\b", r"\bkrasnoyarsk\b",
    r"\bchechnya\b", r"\bgrozny\b", r"\bdagestan\b", r"\bkaliningrad\b",
    r"\bcrimea\b", r"\bsevastopol\b", r"\bkrasnodar\b", r"\birkutsk\b",
    
    # Украина и связанные регионы
    r"\bukraine\b", r"\bukrainian\b", r"\bkyiv\b", r"\bkiev\b", r"\bkharkiv\b",
    r"\bodesa\b", r"\bodessa\b", r"\bdonbas\b", r"\bdonetsk\b", r"\bluhansk\b",
    r"\bzelensky\b", r"\bvolodymyr zelensky\b", r"\bkyiv\b",
    
    # Санкции и экономика
    r"\bsanction[s]?\b", r"\bembargo\b", r"\brestrict\b", r"\bprohibit\b",
    r"\bruble\b", r"\brub\b", r"\brussian ruble\b", r"\beconomy\b", r"\bfinance\b",
    r"\boil\b", r"\bgas\b", r"\bnord\s?stream\b", r"\byamal\b", r"\bsiberia\b",
    r"\bimf\b", r"\bworld bank\b", r"\bswift\b", r"\bcentral bank\b",
    
    # Военные действия и безопасность
    r"\bwar\b", r"\bconflict\b", r"\bmilitary\b", r"\barmy\b", r"\bdefense\b",
    r"\battack\b", r"\bstrike\b", r"\binvasion\b", r"\boccupation\b",
    r"\bnuclear\b", r"\bmissile\b", r"\bdrone\b", r"\btank\b", r"\bsoldier[s]?\b",
    
    # Международные организации и страны-реакторы
    r"\bnato\b", r"\bnorth atlantic treaty\b", r"\beuropa\b", r"\beuropean union\b",
    r"\bgermany\b", r"\bfrance\b", r"\busa\b", r"\bunited states\b", r"\buk\b",
    r"\bbritain\b", r"\bcanada\b", r"\bjapan\b", r"\bsouth korea\b", r"\bpoland\b",
    r"\bfinland\b", r"\bsweden\b", r"\bestonia\b", r"\blatvia\b", r"\blithuania\b",
    
    # Дипломатия и политика
    r"\bdiplomat\b", r"\btalks\b", r"\bnegotiat\b", r"\bmeeting\b", r"\bsummit\b",
    r"\bforeign minister\b", r"\bforeign policy\b", r"\bgeopolitic\b", r"\bsecurity\b",
    
    # Исторические и идеологические термины
    r"\bsoviet\b", r"\bussr\b", r"\bpost\W?soviet\b", r"\bcommunist\b", r"\bkremlin\b"

]

seen_links = set()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger()

def translate(text):
    """Перевод с резервным MyMemoryTranslator"""
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
    """Парсит по одной свежей статье из каждого источника"""
    headers = {"User-Agent": "Mozilla/5.0"}
    messages = []
    for src in SOURCES:
        try:
            resp = requests.get(src["url"], timeout=14, headers=headers)
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
          prefix = get_source_prefix(src["name"]).upper()
           msg = f"<b>{prefix}</b>: {ru_title}\n\n{ru_lead}\n\nИсточник: link"
            messages.append((msg, link))

        except Exception as e:
            log.error(f"Ошибка {src['name']}: {e}")
    return messages

def job_main():
    """Отправка новостей каждые 30 минут"""
    log.info("🔄 Проверка новостей...")
    messages = fetch_one_per_source()
    count = 0
    for msg, link in messages:
        # 🔥 ИСПРАВЛЕНО: убраны пробелы в URL
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id": CHANNEL_ID,
            "text": msg,
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
    log.info("🚀 Бот запущен. Отправка каждые 30 минут.")

    # Первый запуск сразу
    job_main()

    # Каждые 30 минут
    schedule.every(1).minutes.do(job_main)

    while True:
        schedule.run_pending()
        time.sleep(1)
