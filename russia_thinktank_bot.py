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
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
# Исправлено: правильно заданы два канала по умолчанию
CHANNEL_IDS = [cid.strip() for cid in os.getenv("@time_n_John", "@finanosint").split(",") if cid.strip()]
DRY_RUN = os.getenv("DRY_RUN", "0") == "1"

# Список источников — убраны лишние пробелы в URL
SOURCES = [
    {"name": "Good Judgment", "url": "https://goodjudgment.com/feed/"},
    {"name": "Johns Hopkins", "url": "https://www.centerforhealthsecurity.org/feed.xml"},
    {"name": "Metaculus", "url": "https://www.metaculus.com/feed/"},
    {"name": "DNI Global Trends", "url": "https://www.dni.gov/index.php/gt2040-home?format=feed&type=rss"},
    {"name": "RAND Corporation", "url": "https://www.rand.org/rss.xml"},
    {"name": "World Economic Forum", "url": "https://www.weforum.org/en/feeds/rss"},
    {"name": "CSIS", "url": "https://www.csis.org/rss.xml"},
    {"name": "Atlantic Council", "url": "https://www.atlanticcouncil.org/feed/"},
    {"name": "Chatham House", "url": "https://www.chathamhouse.org/feeds/all"},
    {"name": "The Economist", "url": "https://www.economist.com/the-world-this-week/rss.xml"},
    {"name": "Bloomberg Politics", "url": "https://www.bloomberg.com/politics/feeds/site.xml"},
    {"name": "Foreign Affairs", "url": "https://www.foreignaffairs.com/rss.xml"},
    {"name": "CFR", "url": "https://www.cfr.org/rss"},
    {"name": "BBC Future", "url": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml"},
    {"name": "Future Timeline", "url": "https://www.futuretimeline.net/feed/"},
    {"name": "Carnegie Endowment", "url": "https://carnegieendowment.org/rss.xml"},
    {"name": "Bruegel", "url": "https://www.bruegel.org/rss.xml"},
    {"name": "E3G", "url": "https://www.e3g.org/feed/"},
]

# Ключевые слова для фильтрации
KEYWORDS = [
   r"\brussia\b", r"\brussian\b", r"\bputin\b", r"\bmoscow\b", r"\bkremlin\b", r"\bukraine\b", r"\bukrainian\b", r"\bzelensky\b", r"\bkyiv\b", r"\bkiev\b", r"\bcrimea\b", r"\bdonbas\b", r"\bsanction[s]?\b", r"\bgazprom\b", r"\bnord\s?stream\b", r"\bwagner\b", r"\blavrov\b", r"\bshoigu\b", r"\bmedvedev\b", r"\bpeskov\b", r"\bnato\b", r"\beuropa\b", r"\busa\b", r"\bsoviet\b", r"\bussr\b", r"\bpost\W?soviet\b", r"\bsvo\b", r"\bспецоперация\b", r"\bspecial military operation\b", r"\bвойна\b", r"\bwar\b", r"\bconflict\b", r"\bконфликт\b", r"\bнаступление\b", r"\boffensive\b", r"\bатака\b", r"\battack\b", r"\bудар\b", r"\bstrike\b", r"\bобстрел\b", r"\bshelling\b", r"\bдрон\b", r"\bdrone\b", r"\bmissile\b", r"\bракета\b",  r"\bэскалация\b", r"\bescalation\b", r"\bмобилизация\b", r"\bmobilization\b", r"\bфронт\b", r"\bfrontline\b", r"\bзахват\b", r"\bcapture\b", r"\bосвобождение\b", r"\bliberation\b", r"\bбой\b", r"\bbattle\b", r"\bпотери\b", r"\bcasualties\b", r"\bпогиб\b", r"\bkilled\b", r"\bранен\b", r"\binjured\b", r"\bпленный\b", r"\bprisoner of war\b", r"\bпереговоры\b", r"\btalks\b", r"\bперемирие\b", r"\bceasefire\b", r"\bсанкции\b", r"\bsanctions\b", r"\bоружие\b", r"\bweapons\b", r"\bпоставки\b", r"\bsupplies\b", r"\bhimars\b", r"\batacms\b", r"\bhour ago\b", r"\bчас назад\b", r"\bminutos atrás\b", r"\b小时前\b", r"\bbitcoin\b", r"\bbtc\b", r"\bбиткоин\b", r"\b比特币\b", r"\bethereum\b", r"\beth\b", r"\bэфир\b", r"\b以太坊\b", r"\bbinance coin\b", r"\bbnb\b", r"\busdt\b", r"\btether\b", r"\bxrp\b", r"\bripple\b", r"\bcardano\b", r"\bada\b", r"\bsolana\b", r"\bsol\b", r"\bdoge\b", r"\bdogecoin\b", r"\bavalanche\b", r"\bavax\b", r"\bpolkadot\b", r"\bdot\b", r"\bchainlink\b", r"\blink\b", r"\btron\b", r"\btrx\b", r"\bcbdc\b", r"\bcentral bank digital currency\b", r"\bцифровой рубль\b", r"\bdigital yuan\b", r"\beuro digital\b", r"\bdefi\b", r"\bдецентрализованные финансы\b", r"\bnft\b", r"\bnon-fungible token\b", r"\bsec\b", r"\bцб рф\b", r"\bрегуляция\b", r"\bregulation\b", r"\bзапрет\b", r"\bban\b", r"\bмайнинг\b", r"\bmining\b", r"\bhalving\b", r"\bхалвинг\b", r"\bволатильность\b", r"\bvolatility\b", r"\bcrash\b", r"\bкрах\b", r"\b刚刚\b", r"\bدقائق مضت\b", r"\bpandemic\b", r"\bпандемия\b", r"\b疫情\b", r"\bجائحة\b", r"\boutbreak\b", r"\bвспышка\b", r"\bэпидемия\b", r"\bepidemic\b", r"\bvirus\b", r"\bвирус\b", r"\bвирусы\b", r"\b变异株\b",  r"\bvaccine\b", r"\bвакцина\b", r"\b疫苗\b", r"\bلقاح\b", r"\bbooster\b", r"\bбустер\b", r"\bревакцинация\b", r"\bquarantine\b", r"\bкарантин\b", r"\b隔离\b", r"\bحجر صحي\b", r"\blockdown\b", r"\bлокдаун\b", r"\b封锁\b", r"\bmutation\b", r"\bмутация\b", r"\b变异\b", r"\bstrain\b", r"\bштамм\b", r"\bomicron\b", r"\bdelta\b", r"\bbiosafety\b", r"\bбиобезопасность\b", r"\b生物安全\b", r"\blab leak\b", r"\bлабораторная утечка\b", r"\b实验室泄漏\b", r"\bgain of function\b", r"\bусиление функции\b", r"\bwho\b", r"\bвоз\b", r"\bcdc\b", r"\bроспотребнадзор\b", r"\binfection rate\b", r"\bзаразность\b", r"\b死亡率\b", r"\bhospitalization\b", r"\bгоспитализация\b", r"\bقبل ساعات\b", r"\b刚刚报告\b"]

DB_PATH = "seen_titles.db"
INTERVAL_SEC = 180
MAX_DB_SIZE = 5000
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

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
    if not text or not text.strip():
        return ""
    try:
        # Попытка с GoogleTranslator
        result = GoogleTranslator(source='auto', target='ru').translate(text)
        if result and result.strip():
            return result.strip()
    except Exception as e1:
        log.warning(f"GoogleTranslator failed: {e1}")
    
    try:
        # Попытка с MyMemoryTranslator
        result = MyMemoryTranslator(source='auto', target='ru').translate(text)
        if result and result.strip():
            return result.strip()
    except Exception as e2:
        log.warning(f"MyMemoryTranslator also failed: {e2}")
    
    # Если оба переводчика не сработали, возвращаем оригинальный текст
    return text.strip()

def html_escape(text: str) -> str:
    """Экранирование HTML-специальных символов"""
    return text.replace("&", "&amp;").replace("<", "<").replace(">", ">")

# ============= ПОЛУЧЕНИЕ НОВОСТЕЙ =============
def fetch_news():
    items = []
    headers = {"User-Agent": USER_AGENT}
    
    for src in SOURCES:
        try:
            log.info(f"Проверка: {src['name']}")
            resp = requests.get(src["url"], headers=headers, timeout=15)
            
            if resp.status_code != 200:
                log.warning(f"Ошибка при запросе {src['name']}: HTTP {resp.status_code}")
                continue
                
            try:
                # Используем более надежный парсер "xml"
                soup = BeautifulSoup(resp.content, "xml")
            except Exception as e:
                log.warning(f"Не удалось распарсить XML для {src['name']} с lxml: {e}. Пробуем html.parser.")
                soup = BeautifulSoup(resp.content, "html.parser")
            
            # Проверяем, есть ли вообще элементы item
            items_found = soup.find_all("item")
            if not items_found:
                # Попробуем найти entry для Atom фидов
                items_found = soup.find_all("entry")
            
            if not items_found:
                log.warning(f"Не найдены элементы новостей в {src['name']}")
                continue
                
            for item in items_found:
                title = ""
                link = ""
                desc = ""
                
                # Обработка RSS формата
                if item.name == "item":
                    title = clean_text(item.title.get_text()) if item.title else ""
                    # Получаем ссылку из текста или атрибута
                    link = ""
                    if item.link:
                        if item.link.get_text().strip():
                            link = item.link.get_text().strip()
                        elif item.link.get("href"):
                            link = item.link.get("href", "").strip()
                    
                    # Поиск описания
                    desc_tag = item.find("description") or item.find("content:encoded") or item.find("content")
                    if desc_tag:
                        raw = desc_tag.get_text()
                        # Удаляем HTML теги
                        clean_desc = BeautifulSoup(raw, "html.parser").get_text()
                        # Берем первое предложение или первые 250 символов
                        sentences = re.split(r'(?<=[.!?])\s+', clean_desc.strip())
                        desc = sentences[0] if sentences else clean_desc[:250]
                
                # Обработка Atom формата
                elif item.name == "entry":
                    title = clean_text(item.title.get_text()) if item.title else ""
                    link_tag = item.find("link", rel="alternate") or item.find("link")
                    link = link_tag.get("href", "") if link_tag else ""
                    
                    # Поиск описания
                    desc_tag = item.find("summary") or item.find("content")
                    if desc_tag:
                        raw = desc_tag.get_text()
                        clean_desc = BeautifulSoup(raw, "html.parser").get_text()
                        sentences = re.split(r'(?<=[.!?])\s+', clean_desc.strip())
                        desc = sentences[0] if sentences else clean_desc[:250]
                
                if not title or not link:
                    continue
                
                # Проверяем, не видели ли мы эту новость ранее
                if is_title_seen(title):
                    continue
                
                # Помечаем как просмотренное ДО фильтрации по ключевым словам
                mark_title_seen(title)
                
                # Фильтрация по ключевым словам
                if not any(re.search(kw, title, re.IGNORECASE) for kw in KEYWORDS):
                    continue
                
                # Перевод заголовка и описания
                ru_title = translate_to_russian(title)
                ru_desc = translate_to_russian(desc) if desc else ""
                
                # Экранирование HTML
                safe_title = html_escape(ru_title)
                safe_desc = html_escape(ru_desc)
                safe_link = html_escape(link)
                
                # Формирование сообщения в HTML формате
                source_bold = f"<b>{src['name']}</b>"
                msg = f"{source_bold}\n\n{safe_title}\n\n{safe_desc}\n\n[Источник]({link})"
                items.append((msg, title))
                items.append((msg, title))
                
        except Exception as e:
            log.error(f"Ошибка при обработке {src['name']}: {e}")
    
    return items

# ============= ОТПРАВКА В TELEGRAM =============
def send_to_telegram(text: str, channel_ids: list) -> bool:
    if DRY_RUN:
        log.info(f"[ТЕСТ] Сообщение для отправки:\n{text}\n")
        return True
    
    success = True
    for ch_id in channel_ids:
        # Исправлено: убраны пробелы в URL API
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": ch_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            r = requests.post(url, data=payload, timeout=15)
            if r.status_code != 200:
                log.error(f"Не удалось отправить в {ch_id}: {r.text}")
                success = False
            else:
                log.info(f"✅ Сообщение отправлено в {ch_id}")
        except Exception as e:
            log.error(f"Ошибка отправки в {ch_id}: {e}")
            success = False
        time.sleep(0.5)  # избегаем rate limit Telegram API
    
    return success

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
    log.info(f"Health check server запущен на порту {port}")
    server.serve_forever()

# ============= ОСНОВНОЙ ЦИКЛ =============
def main_loop():
    init_db()
    
    # Проверка конфигурации
    if not TELEGRAM_TOKEN:
        log.error("❌ TELEGRAM_TOKEN не установлен!")
        return
    
    if not CHANNEL_IDS:
        log.error("❌ CHANNEL_IDS не установлен! Пример: CHANNEL_IDS=@channel1,@channel2")
        return
    
    log.info(f"🚀 Бот запущен. Каналы: {', '.join(CHANNEL_IDS)}")
    if DRY_RUN:
        log.info("🧪 Режим тестирования (DRY_RUN) включен - сообщения не будут отправляться")
    
    while True:
        try:
            news = fetch_news()
            sent = 0
            total = len(news)
            
            for msg, orig_title in news:
                if send_to_telegram(msg, CHANNEL_IDS):
                    sent += 1
                time.sleep(1)
            
            log.info(f"✅ Цикл завершён. Найдено: {total}, Отправлено: {sent}")
        except Exception as e:
            log.exception(f"Критическая ошибка в основном цикле: {e}")
        time.sleep(INTERVAL_SEC)

# ============= ЗАПУСК =============
if __name__ == "__main__":
    # Запуск health check сервера в отдельном потоке
    threading.Thread(target=start_health_server, daemon=True).start()
    
    # Запуск основного цикла
    main_loop()


