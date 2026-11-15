"""Statická extrakce diskusních příspěvků z discuss.python.org (kategorie Python Help).

Instalace:      python -m pip install requests beautifulsoup4
Jeden běh:      python python_forum_scraper_v2.py data
Trvale:         python python_forum_scraper_v2.py data --watch
Kontrola dat:   python python_forum_scraper_v2.py data --check

Tok: titulní strana kategorie -> seznam témat -> stránky vlákna -> JSONL.
Soubor tématu: <root>/<zdroj>/<rok>/<měsíc>/<zdroj>-<YYMMDD>-<hash8>.jsonl
První řádek je téma, další řádky komentáře; nové komentáře se pouze připojují.

Rozhodnutí, která je vhodné obhájit u obhajoby:
- Datum v cestě je datum PUBLIKACE tématu. Kdyby to bylo datum stažení, vznikne
  každý den jiný soubor pro totéž téma a připojování (mode="a") ztratí smysl.
- parent_id je vždy null. Crawler HTML Discourse neobsahuje odkaz na rodičovský
  příspěvek, takže vztah nelze spolehlivě určit; data se nevymýšlejí.
- likes se berou z meta[itemprop=upvoteCount] u příspěvku (crawler HTML je
  obsahuje). dislikes web nenabízí, proto je vždy null.
- Model je append-only: editace a smazání příspěvků se nepřenášejí.
"""
import argparse
import contextlib
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

BASE = "https://discuss.python.org"
HOST = "discuss.python.org"
# Doména uvedená v záznamu "source"; adresář a prefix ID používají krátký identifikátor.
DOMAIN = "discuss.python.org"
CATEGORY = BASE + "/c/help/7"
SOURCE = "python"
AGENT = "PythonForumSchoolScraper/1.0"
POST = 'div.topic-body.crawler-post[id^="post_"]'
TOPIC_LINK = 'a.raw-topic-link, a.title, a[itemprop="url"]'
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
MIN_TIME = datetime.min.replace(tzinfo=timezone.utc)


class LockBusy(RuntimeError):
    """Nad stejnou složkou už běží jiná instance scraperu."""


def now():
    return datetime.now(timezone.utc)


def stamp(value):
    """Převede ISO 8601 řetězec na čas s časovou zónou; jinak vrací None."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else None


def activity_day(value):
    """Převede text sloupce Activity ('November 14, 2026') na datum."""
    text = " ".join((value or "").split())
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def canonical(href):
    """Vrátí kanonickou URL vlákna, nebo None, pokud odkaz nevede na vlákno."""
    u = urlsplit(urljoin(BASE, href))
    m = re.fullmatch(r"/t/([^/]+)/(\d+)(?:/\d+)?/?", u.path)
    if u.scheme == "https" and u.netloc.lower() == HOST and m:
        return f"{BASE}/t/{m[1]}/{m[2]}"
    return None


def pick(node, selector, attr=None):
    found = node.select_one(selector)
    if found is None:
        return None
    return found.get(attr) if attr else found.get_text(strip=True)


class Web:
    """HTTP klient, který respektuje robots.txt, prodlevu, retry a přesměrování."""

    MAX_HOPS = 5
    RETRIES = 3

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": AGENT, "Accept": "text/html,*/*;q=0.8"})
        self.robot = RobotFileParser()
        self.delay = 2.0
        self.last = 0.0
        self.robot.parse(self.fetch(BASE + "/robots.txt", check=False).splitlines())
        self.delay = max(2.0, float(self.robot.crawl_delay(AGENT) or 0))

    @staticmethod
    def _check_host(url):
        u = urlsplit(url)
        if u.scheme != "https" or u.netloc.lower() != HOST:
            raise ValueError(f"Cizí adresa: {url}")

    def _wait(self):
        time.sleep(max(0.0, self.delay - (time.monotonic() - self.last)))
        self.last = time.monotonic()

    @staticmethod
    def _retry_after(response, default):
        raw = (response.headers.get("Retry-After") or "").strip()
        if raw.isdigit():
            return float(raw)
        if raw:
            try:
                return max(0.0, (parsedate_to_datetime(raw) - now()).total_seconds())
            except (TypeError, ValueError):
                pass
        return default

    def _request(self, url):
        response = None
        for attempt in range(1, self.RETRIES + 1):
            self._wait()
            try:
                response = self.session.get(url, timeout=25, allow_redirects=False)
            except requests.RequestException:
                if attempt == self.RETRIES:
                    raise
                time.sleep(min(30.0, 5.0 * 2 ** (attempt - 1)))
                continue
            if response.status_code in RETRY_STATUS and attempt < self.RETRIES:
                wait = min(300.0, self._retry_after(response, 5.0 * 2 ** (attempt - 1)))
                logging.warning("HTTP %s u %s, čekám %.0f s", response.status_code, url, wait)
                time.sleep(wait)
                continue
            return response
        return response

    def fetch(self, url, check=True):
        for _ in range(self.MAX_HOPS):
            self._check_host(url)
            if check and not self.robot.can_fetch(AGENT, url):
                raise ValueError(f"Cesta zakázaná v robots.txt: {url}")
            response = self._request(url)
            if response.is_redirect:
                target = urljoin(url, response.headers.get("Location", ""))
                self._check_host(target)
                source, destination = canonical(url), canonical(target)
                if source and destination and source != destination:
                    raise ValueError(f"Přesměrování do jiného vlákna: {target}")
                url = target
                continue
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError(f"Neočekávaný stav HTTP {response.status_code}: {url}")
            return response.text
        raise ValueError(f"Příliš mnoho přesměrování: {url}")

    def soup(self, url):
        return BeautifulSoup(self.fetch(url), "html.parser")


def discover(soup):
    """Vrátí {číslo vlákna: (url, titulek, datum aktivity)} z titulní strany."""
    topics = {}
    for row in soup.select("tr.topic-list-item, li.topic-list-item"):
        link = row.select_one(TOPIC_LINK)
        if link is None:
            continue
        url = canonical(link.get("href", ""))
        if not url:
            continue
        number = url.rsplit("/", 1)[1]
        if number in topics:
            continue
        day = None
        machine = pick(row, 'meta[itemprop="dateModified"]', "content")
        machine = machine or pick(row, 'td:last-child time[datetime], .activity time[datetime]', "datetime")
        parsed = stamp(machine)
        if parsed is not None:
            day = parsed.date()
        else:
            cells = row.select("td")
            day = activity_day(cells[-1].get_text(" ", strip=True)) if cells else None
        topics[number] = (url, link.get_text(" ", strip=True), day)
    if not topics:
        raise ValueError(
            "V HTML kategorie nebyla nalezena žádná témata "
            "(server nevrátil crawler HTML, nebo se změnila struktura stránky)."
        )
    return topics


def read_topic(web, url, number, title, key, max_pages):
    """Stáhne vlákno. Vrací (téma, komentáře, complete, čas posledního příspěvku)."""
    page, seen, posts, topic = url, set(), {}, None
    captured = now().isoformat()
    last_post = None
    complete = True
    while page:
        if page in seen:
            raise ValueError(f"Smyčka ve stránkování: {page}")
        if max_pages and len(seen) >= max_pages:
            logging.warning("Překročen --max-pages (%d) u %s, ukládám částečná data.", max_pages, url)
            complete = False
            break
        seen.add(page)
        soup = web.soup(page)
        if not soup.select_one(POST):
            raise ValueError(f"Stránka neobsahuje příspěvky: {page}")
        before = len(posts)
        for post in soup.select(POST):
            pos = post["id"].removeprefix("post_")
            if not pos.isdecimal():
                continue
            published = stamp(pick(post, "time.post-time", "datetime"))
            body = post.select_one('.post[itemprop="text"]')
            if published is None or body is None:
                if pos == "1":
                    raise ValueError(f"Chybí metadata úvodního příspěvku: {url}")
                logging.warning("Přeskakuji neúplný příspěvek %s/%s", number, pos)
                continue
            author = pick(post, '.creator [itemprop="name"]')
            if pos == "1":
                topic = dict(
                    type="topic",
                    topic_id=key,
                    source=DOMAIN,
                    url=url,
                    title=pick(soup, "#topic-title h1") or title,
                    author=author,
                    published_at=published.isoformat(),
                    scraped_at=captured,
                )
            else:
                cid = f"{SOURCE}_c_{number}_{pos}"
                likes = pick(post, ':scope > meta[itemprop="upvoteCount"]', "content")
                posts.setdefault(
                    cid,
                    dict(
                        type="comment",
                        comment_id=cid,
                        topic_id=key,
                        parent_id=None,
                        author=author,
                        published_at=published.isoformat(),
                        scraped_at=captured,
                        text=body.get_text().strip(),
                        likes=int(likes) if likes and likes.isdecimal() else None,
                        dislikes=None,
                    ),
                )
                if last_post is None or published > last_post:
                    last_post = published
        next_link = pick(soup, 'link[rel="next"], a[rel="next"]', "href")
        if len(seen) > 1 and len(posts) == before:
            raise ValueError(f"Stránka nepřinesla nové příspěvky: {page}")
        page = urljoin(page, next_link) if next_link else None
        if page and (canonical(page) or "").rsplit("/", 1)[-1] != number:
            raise ValueError(f"Odkaz Další nevede do téhož vlákna: {page}")
    if topic is None:
        raise ValueError(f"Chybí úvodní příspěvek: {url}")
    if last_post is None:
        last_post = stamp(topic["published_at"])
    return topic, list(posts.values()), complete, last_post


def append_topic(root, topic, comments, suffix):
    """Připojí nové komentáře. Vrací (počet nových, celkový počet komentářů)."""
    dt = stamp(topic["published_at"])
    if dt is None:
        raise ValueError("Téma nemá platné published_at.")
    directory = root / SOURCE / f"{dt:%Y}" / f"{dt:%m}"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{SOURCE}-{dt:%y%m%d}-{suffix}.jsonl"
    existing = []
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    existing.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Poškozený JSONL {path}:{lineno}: {exc.msg}") from exc
        if (
            not existing
            or existing[0].get("type") != "topic"
            or existing[0].get("topic_id") != topic["topic_id"]
        ):
            raise ValueError(f"Nesouhlasí hlavička souboru: {path}")
    known = {item.get("comment_id") for item in existing if item.get("type") == "comment"}
    new = [c for c in comments if c["comment_id"] not in known]
    rows = new if existing else [topic, *new]
    with path.open("a", encoding="utf-8") as f:
        if rows:
            f.write("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in rows))
        f.flush()
        os.fsync(f.fileno())
    return len(new), len(known) + len(new)


def load_state(path):
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("kořen není objekt")
    except (OSError, ValueError) as exc:
        broken = path.with_name(f"state.corrupt-{now():%Y%m%d%H%M%S}.json")
        logging.error("state.json nelze načíst (%s), odkládám do %s", exc, broken.name)
        with contextlib.suppress(OSError):
            path.replace(broken)
        return {}
    return data


def save_state(path, data):
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


@contextlib.contextmanager
def single_instance(path):
    """Zámek nad složkou; na Windows msvcrt, jinde fcntl. Drží se po dobu běhu."""
    handle = path.open("a+")
    locked = False
    try:
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError as exc:
            raise LockBusy(str(path)) from exc
        yield
    finally:
        if locked:
            with contextlib.suppress(OSError):
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def run(args):
    state_file = args.root / "state.json"
    state = load_state(state_file)
    processed = set(state.get("processed_topics", []))
    learned = dict(state.get("last_activity", {}))
    urls = dict(state.get("topic_urls", {}))
    cutoff = now() - timedelta(hours=args.active_hours)
    cutoff_day = cutoff.date()
    web = Web()
    scraped = 0
    try:
        topics = discover(web.soup(CATEGORY))

        def active(day, key):
            if day is not None and day >= cutoff_day:
                return True
            seen_at = stamp(learned.get(key))
            return seen_at is not None and seen_at >= cutoff

        candidates = []
        for number, (url, title, day) in topics.items():
            # Zachová původní URL a hash, i když se později změní slug.
            identity = urls.get(number, url)
            suffix = hashlib.md5(identity.encode("utf-8")).hexdigest()[-8:]
            key = f"{SOURCE}_{suffix}"
            if key in processed and not active(day, key):
                logging.debug("%s: neaktivní, přeskakuji", key)
                continue
            seen_at = stamp(learned.get(key)) or MIN_TIME
            candidates.append((key in processed, seen_at, int(number), key, identity, suffix, url, title))
        # Nejdřív nezpracovaná témata, pak ta nejdéle nekontrolovaná: --limit nic nevyhladoví.
        candidates.sort(key=lambda c: (c[0], c[1], c[2]))

        for _, _, number, key, identity, suffix, url, title in candidates:
            if args.limit and scraped >= args.limit:
                break
            try:
                topic, comments, complete, last = read_topic(
                    web, url, str(number), title, key, args.max_pages
                )
                count, total = append_topic(args.root, topic, comments, suffix)
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status in (403, 429):
                    logging.warning("Server omezil přístup (HTTP %s), ukončuji cyklus.", status)
                    break
                logging.warning("%s: %s", url, exc)
                continue
            except (requests.RequestException, ValueError, OSError) as exc:
                logging.warning("%s: %s", url, exc)
                continue
            scraped += 1
            urls[str(number)] = identity
            if complete:
                processed.add(key)
            learned[key] = last.isoformat()
            logging.info(
                "%s: +%d komentářů (celkem %d)%s",
                key, count, total, "" if complete else " [neúplné]",
            )

        save_state(
            state_file,
            dict(
                last_run=now().isoformat(),
                processed_topics=sorted(processed),
                topic_urls=urls,
                last_activity=dict(sorted(learned.items())),
            ),
        )
    finally:
        web.session.close()


def validate(root):
    """Zkontroluje datový model uložených JSONL souborů. Vrací návratový kód."""
    files = sorted(root.rglob("*.jsonl"))
    if not files:
        print(f"Nenalezeny žádné .jsonl soubory v {root}.")
        return 1
    problems = []
    comments_total = 0
    for path in files:
        rel = path.relative_to(root)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            problems.append(f"{rel}: nelze číst ({exc})")
            continue
        records = []
        for lineno, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                problems.append(f"{rel}:{lineno}: neplatný JSON ({exc.msg})")
                continue
            if not isinstance(obj, dict):
                problems.append(f"{rel}:{lineno}: řádek není JSON objekt")
                continue
            records.append(obj)
        if not records:
            problems.append(f"{rel}: prázdný soubor")
            continue
        topic = records[0]
        if topic.get("type") != "topic":
            problems.append(f"{rel}: první řádek není type=topic")
            continue
        url = topic.get("url") or ""
        suffix = hashlib.md5(url.encode("utf-8")).hexdigest()[-8:]
        if topic.get("topic_id") != f"{SOURCE}_{suffix}":
            problems.append(f"{rel}: topic_id neodpovídá MD5 z url")
        if topic.get("source") != DOMAIN:
            problems.append(f"{rel}: source != {DOMAIN}")
        for field in ("url", "title", "published_at", "scraped_at"):
            if not topic.get(field):
                problems.append(f"{rel}: téma nemá pole {field}")
        if "author" not in topic:
            problems.append(f"{rel}: téma nemá pole author")
        dt = stamp(topic.get("published_at"))
        if dt is None:
            problems.append(f"{rel}: published_at není ISO 8601 s časovou zónou")
        elif len(rel.parts) == 4:
            source, year, month, name = rel.parts
            if source != SOURCE:
                problems.append(f"{rel}: adresář zdroje != {SOURCE}")
            if (year, month) != (f"{dt:%Y}", f"{dt:%m}"):
                problems.append(f"{rel}: adresář roku/měsíce neodpovídá published_at")
            if name != f"{SOURCE}-{dt:%y%m%d}-{suffix}.jsonl":
                problems.append(f"{rel}: název souboru neodpovídá datu a hashi")
        else:
            problems.append(f"{rel}: neočekávaná hloubka cesty")
        ids = set()
        for rec in records[1:]:
            if rec.get("type") != "comment":
                problems.append(f"{rel}: záznam typu {rec.get('type')!r} mezi komentáři")
                continue
            for field in (
                "comment_id", "topic_id", "author", "published_at",
                "scraped_at", "text", "likes", "dislikes",
            ):
                if field not in rec:
                    problems.append(f"{rel}: komentář nemá pole {field}")
            if rec.get("topic_id") != topic.get("topic_id"):
                problems.append(f"{rel}: komentář {rec.get('comment_id')} má cizí topic_id")
            if not str(rec.get("comment_id", "")).startswith(f"{SOURCE}_c_"):
                problems.append(f"{rel}: comment_id {rec.get('comment_id')} nemá prefix {SOURCE}_c_")
            if rec.get("comment_id") in ids:
                problems.append(f"{rel}: duplicitní comment_id {rec.get('comment_id')}")
            ids.add(rec.get("comment_id"))
            if stamp(rec.get("published_at")) is None or stamp(rec.get("scraped_at")) is None:
                problems.append(f"{rel}: komentář {rec.get('comment_id')} nemá platné časy")
            if not isinstance(rec.get("text"), str):
                problems.append(f"{rel}: komentář {rec.get('comment_id')} nemá text")
        for rec in records[1:]:
            parent = rec.get("parent_id")
            if parent is not None and parent not in ids:
                problems.append(f"{rel}: parent_id {parent} neexistuje")
        comments_total += len(records) - 1

    for problem in problems:
        print(f"CHYBA {problem}")
    print(f"Souborů: {len(files)}, komentářů: {comments_total}, chyb: {len(problems)}")
    return 1 if problems else 0


def loop(args):
    while True:
        started = time.monotonic()
        try:
            run(args)
        except (requests.RequestException, ValueError, OSError) as exc:
            logging.error("Cyklus selhal: %s", exc)
            if not args.watch:
                return 1
        if not args.watch:
            return 0
        time.sleep(max(0.0, 3600 - (time.monotonic() - started)))


def main():
    parser = argparse.ArgumentParser(description="Statická extrakce diskusí Python Help.")
    parser.add_argument("root", type=Path, help="Kořen dat a souboru state.json")
    parser.add_argument("--watch", action="store_true", help="Opakovat každou hodinu")
    parser.add_argument("--limit", type=int, default=20, help="Max. počet témat na běh (0 = bez limitu)")
    parser.add_argument("--max-pages", type=int, default=30, help="Max. stránek vlákna (0 = bez limitu)")
    parser.add_argument("--active-hours", type=int, default=24, help="Okno aktivity tématu v hodinách")
    parser.add_argument("--log-file", type=Path, help="Zapisovat log i do souboru (rotace 1 MB, 3 soubory)")
    parser.add_argument("--check", action="store_true", help="Jen zkontrolovat existující JSONL data")
    args = parser.parse_args()
    if min(args.limit, args.max_pages, args.active_hours) < 0:
        parser.error("Číselné parametry nesmí být záporné.")
    if args.active_hours < 1:
        parser.error("--active-hours musí být kladné.")

    handlers = [logging.StreamHandler()]
    if args.log_file:
        args.log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(args.log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )

    args.root.mkdir(parents=True, exist_ok=True)
    if args.check:
        return validate(args.root)
    try:
        with single_instance(args.root / ".scraper.lock"):
            return loop(args)
    except LockBusy:
        logging.error("Nad %s už běží jiná instance, končím.", args.root)
        return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
