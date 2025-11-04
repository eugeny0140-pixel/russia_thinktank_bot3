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
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

# ============= НАСТРОЙКИ =============
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHANNEL_IDS = [cid.strip() for cid in os.getenv("CHANNEL_IDS", "@time_n_John,@finanosint").split(",") if cid.strip()]
DRY_RUN = os.getenv("DRY_RUN", "0") == "1"
RENDER_APP_URL = os.getenv("RENDER_APP_URL", "")  # URL вашего приложения на Render для keep-alive

# Список источников — убраны лишние пробелы в URL
SOURCES = [
    {"name": "Good Judgment", "url": "https://goodjudgment.com/feed/"},
    {"name": "Johns Hopkins", "url": "https://www.centerforhealthsecurity.org/feed.xml"},
    {"name": "Metaculus", "url": "https://www.metaculus.com/feed/"},
    {"name": "DNI Global Trends", "url": "https://www.dni.gov/index.php/gt2040-home?format=feed&type=rss"},
    {"name": "RAND Corporation", "url": "https://www.rand.org/feed/"},
    {"name": "World Economic Forum", "url": "https://www.weforum.org/feed/"},
    {"name": "CSIS", "url": "https://www.csis.org/feed/"},
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

DB_PATH = "seen_titles.db"
INTERVAL_SEC = 300  # 5 минут
MAX_DB_SIZE = 5000
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
MAX_WORKERS = 5  # Количество потоков для параллельной обработки источников
TELEGRAM_MAX_CHARS = 4096  # Максимальная длина сообщения в Telegram

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
        # Создаем индекс для ускорения удаления старых записей
        conn.execute("CREATE INDEX IF NOT EXISTS idx_processed_at ON seen_titles(processed_at)")
        conn.commit()

def normalize_title(title: str) -> str:
    return re.sub(r"[^a-zA-Zа-яА-Я0-9ёЁ]", "", title.lower()).strip()

def is_title_seen(title: str) -> bool:
    norm = normalize_title(title)
    if not norm:
        return False
    h = hashlib.sha256(norm.encode("utf-8")).hexdigest()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        cur = conn.execute("SELECT 1 FROM seen_titles WHERE title_hash = ?", (h,))
        return cur.fetchone() is not None

def mark_title_seen(title: str):
    norm = normalize_title(title)
    if not norm:
        return
    h = hashlib.sha256(norm.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    try:
        with sqlite3.connect(DB_PATH, timeout=10) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO seen_titles (title_hash, processed_at) VALUES (?, ?)",
                (h, now)
            )
            # Оптимизированное удаление старых записей
            conn.execute(f"""
                DELETE FROM seen_titles
                WHERE rowid NOT IN (
                    SELECT rowid FROM seen_titles
                    ORDER BY processed_at DESC
                    LIMIT {MAX_DB_SIZE}
                )
            """)
            conn.commit()
    except sqlite3.OperationalError as e:
        log.error(f"Ошибка работы с базой данных: {e}. Попытка повтора через 1 секунду")
        time.sleep(1)
        # Повторяем попытку один раз
        try:
            with sqlite3.connect(DB_PATH, timeout=10) as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO seen_titles (title_hash, processed_at) VALUES (?, ?)",
                    (h, now)
                )
                conn.commit()
        except Exception as e2:
            log.error(f"Повторная попытка записи в БД также не удалась: {e2}")

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
    return text.replace("&", "&amp;").replace("<", "<").replace(">", ">").replace('"', "&quot;")

def truncate_message(text: str, max_length: int = TELEGRAM_MAX_CHARS) -> str:
    """Обрезает сообщение до максимальной длины, сохраняя целостность HTML-тегов"""
    if len(text) <= max_length:
        return text
    
    # Пытаемся обрезать до последней полной строки
    truncated = text[:max_length]
    last_newline = truncated.rfind("\n")
    if last_newline > max_length * 0.8:  # Если перенос близко к концу
        truncated = truncated[:last_newline]
    
    # Проверяем и закрываем незакрытые HTML-теги
    open_tags = []
    pos = 0
    while pos < len(truncated):
        if truncated[pos] == "<":
            end_tag = truncated.find(">", pos)
            if end_tag != -1:
                tag_content = truncated[pos+1:end_tag]
                if tag_content.startswith("/"):
                    # Закрывающий тег
                    if open_tags:
                        open_tags.pop()
                elif not tag_content.endswith("/"):
                    # Открывающий тег (не самозакрывающийся)
                    tag_name = tag_content.split()[0]
                    open_tags.append(tag_name)
                pos = end_tag
        pos += 1
    
    # Добавляем закрывающие теги
    for tag in reversed(open_tags):
        truncated += f"</{tag}>"
    
    truncated += "..."
    return truncated

def keep_awake():
    """Функция для предотвращения засыпания приложения на Render.com"""
    if not RENDER_APP_URL:
        log.info("RENDER_APP_URL не установлен. Keep-alive отключен.")
        return
        
    log.info(f"Keep-alive активен. URL для пинга: {RENDER_APP_URL}")
    while True:
        try:
            requests.get(RENDER_APP_URL, timeout=10)
            log.debug("✅ Keep-alive запрос отправлен успешно")
        except Exception as e:
            log.warning(f"Не удалось выполнить keep-alive запрос: {e}")
        # Отправляем запрос каждые 10 минут (Render засыпает после 15 минут бездействия)
        time.sleep(600)

# ============= ПОЛУЧЕНИЕ НОВОСТЕЙ =============
def process_source(src):
    """Обработка одного источника новостей"""
    headers = {"User-Agent": USER_AGENT}
    items = []
    
    try:
        log.info(f"Проверка: {src['name']}")
        resp = requests.get(src["url"], headers=headers, timeout=20)
        
        if resp.status_code != 200:
            log.warning(f"Ошибка при запросе {src['name']}: HTTP {resp.status_code}")
            return items
            
        # Проверяем тип контента для DNI Global Trends (возвращает HTML вместо XML)
        content_type = resp.headers.get('Content-Type', '').lower()
        use_html_parser = 'html' in content_type or 'dni.gov' in src['url']
        
        try:
            # Для DNI Global Trends используем html.parser вместо xml
            parser = "html.parser" if use_html_parser else "xml"
            soup = BeautifulSoup(resp.content, parser)
            
            # Для DNI Global Trends специальная обработка
            if 'dni.gov' in src['url'] and use_html_parser:
                # Ищем RSS-ссылки в HTML
                rss_links = soup.find_all('link', {'type': 'application/rss+xml'})
                if rss_links:
                    rss_url = rss_links[0].get('href')
                    if not rss_url.startswith('http'):
                        rss_url = 'https://www.dni.gov' + rss_url
                    # Получаем фактический RSS
                    rss_resp = requests.get(rss_url, headers=headers, timeout=15)
                    if rss_resp.status_code == 200:
                        soup = BeautifulSoup(rss_resp.content, "xml")
            elif use_html_parser:
                log.warning(f"{src['name']} вернул HTML вместо XML. Пробуем извлечь новости из HTML.")
        except Exception as e:
            log.warning(f"Не удалось распарсить контент для {src['name']}: {e}. Пробуем html.parser.")
            soup = BeautifulSoup(resp.content, "html.parser")
        
        # Проверяем, есть ли вообще элементы item
        items_found = soup.find_all("item")
        if not items_found:
            # Попробуем найти entry для Atom фидов
            items_found = soup.find_all("entry")
        
        if not items_found:
            # Попытка найти альтернативные элементы для HTML-страниц
            if use_html_parser and 'dni.gov' in src['url']:
                # Поиск новостей на странице DNI
                articles = soup.select('article, .news-item, .post')
                for article in articles[:10]:  # Берем не более 10 последних статей
                    title_elem = article.find('h2', class_='title') or article.find('h3') or article.find('a', class_='title')
                    if title_elem:
                        title = clean_text(title_elem.get_text())
                        link = title_elem.get('href', '') if title_elem.name == 'a' else ''
                        if link and not link.startswith('http'):
                            link = 'https://www.dni.gov' + link
                        desc_elem = article.find('p', class_='summary') or article.find('div', class_='content') or article.find('p')
                        desc = clean_text(desc_elem.get_text()) if desc_elem else ""
                        
                        if title and link:
                            items.append((title, link, desc, src))
            else:
                log.warning(f"Не найдены элементы новостей в {src['name']}")
            return items
        
        for item in items_found:
            try:
                title = ""
                link = ""
                desc = ""
                
                # Обработка RSS формата
                if item.name == "item":
                    title = clean_text(item.title.get_text()) if item.title else ""
                    # Получаем ссылку из текста или атрибута
                    link = ""
                    if item.link:
                        if isinstance(item.link, str):
                            link = item.link.strip()
                        elif hasattr(item.link, 'get_text'):
                            link_text = item.link.get_text().strip()
                            link = link_text if link_text else item.link.get("href", "").strip()
                        elif hasattr(item.link, 'get'):
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
                
                items.append((title, link, desc, src))
            except Exception as e:
                log.error(f"Ошибка при обработке элемента в {src['name']}: {e}")
                continue
    
    except Exception as e:
        log.error(f"Критическая ошибка при обработке {src['name']}: {e}")
    
    return items

def fetch_news():
    """Получение новостей из всех источников с использованием многопоточности"""
    all_items = []
    source_items = []
    
    # Используем ThreadPoolExecutor для параллельной обработки источников
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_source = {executor.submit(process_source, src): src for src in SOURCES}
        for future in as_completed(future_to_source):
            src = future_to_source[future]
            try:
                items = future.result()
                source_items.extend(items)
            except Exception as e:
                log.error(f"Ошибка при получении новостей из {src['name']}: {e}")
    
    # Фильтрация и подготовка сообщений
    for title, link, desc, src in source_items:
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
        msg = f"{source_bold}\n\n<strong>{safe_title}</strong>\n\n{safe_desc}\n\n<a href='{safe_link}'>Источник</a>"
        
        # Обрезаем сообщение, если оно слишком длинное
        msg = truncate_message(msg)
        
        all_items.append((msg, title))
    
    log.info(f"Найдено {len(all_items)} новых релевантных новостей")
    return all_items

# ============= ОТПРАВКА В TELEGRAM =============
def send_to_telegram(text: str, channel_ids: list) -> bool:
    if DRY_RUN:
        log.info(f"[ТЕСТ] Сообщение для отправки:\n{text[:200]}...\n")
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
        
        # Попытка отправки с обработкой ошибок 429
        max_retries = 5
        for attempt in range(max_retries):
            try:
                r = requests.post(url, data=payload, timeout=30)
                
                if r.status_code == 200:
                    log.info(f"✅ Сообщение отправлено в {ch_id}")
                    break
                elif r.status_code == 429:
                    # Обработка ошибки "Too Many Requests"
                    try:
                        response = r.json()
                        retry_after = response.get('parameters', {}).get('retry_after', 30)
                    except:
                        retry_after = 30
                    
                    log.warning(f"⚠️ Ограничение запросов для {ch_id}. Повторная попытка через {retry_after} секунд...")
                    time.sleep(retry_after + attempt * 5)  # Экспоненциальная задержка
                    continue
                elif r.status_code == 400 and "message is too long" in r.text.lower():
                    # Сообщение слишком длинное, пытаемся его обрезать
                    log.warning(f"Сообщение слишком длинное для {ch_id}. Попытка обрезки...")
                    text = truncate_message(text, TELEGRAM_MAX_CHARS - 100)  # Оставляем запас
                    payload["text"] = text
                    continue
                else:
                    log.error(f"❌ Не удалось отправить в {ch_id}: HTTP {r.status_code}, ответ: {r.text}")
                    success = False
                    break
            except Exception as e:
                log.error(f"❌ Ошибка отправки в {ch_id}: {e}")
                success = False
                break
        else:
            log.error(f"❌ Превышено количество попыток отправки в {ch_id}")
            success = False
        
        # Увеличиваем задержку между отправками в разные каналы
        time.sleep(2.0)
    
    return success

# ============= HEALTH CHECK =============
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        
        status = {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "channels": CHANNEL_IDS,
            "sources_count": len(SOURCES),
            "db_path": DB_PATH
        }
        self.wfile.write(json.dumps(status).encode('utf-8'))
    
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
    log.info(f"🔄 Проверка источников каждые {INTERVAL_SEC} секунд")
    
    if DRY_RUN:
        log.info("🧪 Режим тестирования (DRY_RUN) включен - сообщения не будут отправляться")
    
    if RENDER_APP_URL:
        log.info("💤 Keep-alive активирован для предотвращения засыпания на Render.com")
    else:
        log.warning("💤 RENDER_APP_URL не установлен. Приложение может засыпать на Render.com.")
    
    while True:
        cycle_start = time.time()
        try:
            news = fetch_news()
            sent = 0
            total = len(news)
            
            # Ограничение количества отправляемых новостей за цикл
            MAX_NEWS_PER_CYCLE = 15
            if total > MAX_NEWS_PER_CYCLE:
                log.warning(f"Найдено {total} новостей, будет отправлено только первые {MAX_NEWS_PER_CYCLE}")
                news = news[:MAX_NEWS_PER_CYCLE]
            
            for msg, orig_title in news:
                if send_to_telegram(msg, CHANNEL_IDS):
                    sent += 1
                # Задержка между отправками сообщений
                time.sleep(1.5)
            
            cycle_duration = time.time() - cycle_start
            log.info(f"✅ Цикл завершён. Найдено: {total}, Отправлено: {sent}, Длительность: {cycle_duration:.1f} сек")
        except Exception as e:
            log.exception(f"Критическая ошибка в основном цикле: {e}")
        
        # Учитываем время выполнения цикла при расчете задержки
        elapsed = time.time() - cycle_start
        sleep_time = max(1, INTERVAL_SEC - elapsed)
        log.debug(f"😴 Следующая проверка через {sleep_time:.1f} секунд")
        time.sleep(sleep_time)

# ============= ЗАПУСК =============
if __name__ == "__main__":
    # Запуск health check сервера в отдельном потоке
    threading.Thread(target=start_health_server, daemon=True).start()
    
    # Запуск keep-alive для предотвращения засыпания на Render.com
    if RENDER_APP_URL:
        threading.Thread(target=keep_awake, daemon=True).start()
    
    # Запуск основного цикла
    main_loop()
