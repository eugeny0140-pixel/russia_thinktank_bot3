import os
import re
import time
import logging
import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
import schedule
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@time_n_John")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан")

SOURCES = [
    "https://www.e3g.org/feed/",
    "https://www.foreignaffairs.com/rss.xml",
    "https://reutersinstitute.politics.ox.ac.uk/rss.xml",
    "https://www.bruegel.org/rss.xml",
    "https://www.csis.org/rss.xml",
    "https://www.atlanticcouncil.org/feed/",
    "https://www.rand.org/rss.xml",
    "https://www.cfr.org/rss/",
    "https://carnegieendowment.org/rss.xml",
]

KEYWORDS = [
    r"\brussia\b", r"\brussian\b", r"\bputin\b", r"\bukraine\b", r"\bzelensky\b",
    r"\bkremlin\b", r"\bmoscow\b", r"\bsanction[s]?\b", r"\bgazprom\b",
    r"\bnord\s?stream\b", r"\bwagner\b", r"\blavrov\b", r"\bnato\b", r"\bwar\b"
]

seen_links = set()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger()

def translate(text):
    try:
        return GoogleTranslator(source='auto', target='ru').translate(text)
    except:
        return text

def escape_md(text):
    for c in r'_*[]()~`>#+-=|{}.!':
        text = text.replace(c, '\\' + c)
    return text

def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, data=data, timeout=10)
        log.info("✅ Отправлено" if r.status_code == 200 else f"❌ Ошибка: {r.text}")
    except Exception as e:
        log.error(f"❌ Исключение: {e}")

def job():
    log.info("🔄 Проверка новостей...")
    headers = {"User-Agent": "Mozilla/5.0"}
    count = 0
    for url in SOURCES:
        try:
            resp = requests.get(url, timeout=20, headers=headers)
            soup = BeautifulSoup(resp.content, "xml")
            for item in soup.find_all("item"):
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
                safe_title = escape_md(ru_title)
                safe_desc = escape_md(ru_desc)
                msg = f"{safe_title}\n\n{safe_desc}\n\n[Источник]({link})"

                send_to_telegram(msg)
                seen_links.add(link)
                count += 1
                time.sleep(2)  # ← увеличена задержка до 2 секунд

        except Exception as e:
            log.error(f"Ошибка при парсинге {url}: {e}")

    log.info(f"📭 Проверка завершена. Отправлено: {count} новостей.")

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
    log.info("🚀 Бот запущен. Проверка в :00 и :30 каждого часа.")

    # Первый запуск при старте
    job()

    # Точное расписание
    schedule.every().hour.at(":00").do(job)
    schedule.every().hour.at(":30").do(job)

    while True:
        schedule.run_pending()
        time.sleep(1)
