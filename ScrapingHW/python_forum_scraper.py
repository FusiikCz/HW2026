"""Instalace: python -m pip install requests beautifulsoup4
Jednou: python python_forum_scraper.py data
Každou hodinu: python python_forum_scraper.py data --watch
Spouštějte pouze jednu instanci nad stejnou složkou.
"""
import argparse
import hashlib
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

BASE = "https://discuss.python.org"
CATEGORY = BASE + "/c/help/7"
SOURCE = "python"
AGENT = "PythonForumSchoolScraper"
POST = 'div.topic-body.crawler-post[id^="post_"]'


def now():
    return datetime.now(timezone.utc)


def stamp(value):
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else None


def canonical(href):
    u = urlsplit(urljoin(BASE, href))
    m = re.fullmatch(r"/t/([^/]+)/(\d+)(?:/\d+)?/?", u.path)
    if u.scheme == "https" and u.netloc == "discuss.python.org" and m:
        return f"{BASE}/t/{m[1]}/{m[2]}"
    return None


def pick(node, selector, attr=None):
    found = node.select_one(selector)
    if found is None:
        return None
    return found.get(attr) if attr else found.get_text(strip=True)


class Web:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = AGENT + "/1.0"
        self.robot = RobotFileParser()
        self.last = 0
        self.robot.parse(self.fetch(BASE + "/robots.txt", check=False).splitlines())

    def fetch(self, url, check=True):
        u = urlsplit(url)
        if u.scheme != "https" or u.netloc != "discuss.python.org":
            raise ValueError(f"Cizí adresa: {url}")
        if check and not self.robot.can_fetch(AGENT, url):
            raise ValueError(f"Cesta zakázaná v robots.txt: {url}")
        delay = max(2, self.robot.crawl_delay(AGENT) or 0)
        time.sleep(max(0, delay - (time.monotonic() - self.last)))
        self.last = time.monotonic()
        response = self.session.get(url, timeout=25, allow_redirects=False)
        response.raise_for_status()
        if response.status_code != 200:
            raise ValueError(f"Neočekávaný stav HTTP {response.status_code}: {url}")
        return response.text

    def soup(self, url):
        return BeautifulSoup(self.fetch(url), "html.parser")


def discover(soup):
    topics = {}
    for row in soup.select("tr"):
        link = row.select_one('a.title, a.raw-topic-link, a[itemprop="url"]')
        if not link or not canonical(link.get("href", "")):
            link = row.select_one('a[href*="/t/"]')
        url = canonical(link.get("href", "")) if link else None
        if not url:
            continue
        activity = pick(row, 'meta[itemprop="dateModified"]', "content")
        activity = activity or pick(row, "td:last-child time[datetime]", "datetime")
        topics.setdefault(url.rsplit("/", 1)[1], (url, link.get_text(" ", strip=True), activity))
    if not topics:
        raise ValueError("V HTML kategorie nebyla nalezena žádná témata.")
    return topics


def read_topic(web, url, number, title, key, max_pages):
    page, seen, posts, topic = url, set(), {}, None
    captured = now().isoformat()
    while page:
        if page in seen or len(seen) >= max_pages:
            raise ValueError(f"Smyčka nebo překročený limit stránek: {page}")
        seen.add(page)
        soup = web.soup(page)
        before = len(posts)
        for post in soup.select(POST):
            pos = post["id"].removeprefix("post_")
            if not pos.isdecimal():
                continue
            published = stamp(pick(post, "time.post-time", "datetime"))
            body = post.select_one('.post[itemprop="text"]')
            if published is None or body is None:
                raise ValueError(f"Neúplný příspěvek {number}/{pos}")
            author = pick(post, '.creator [itemprop="name"]')
            common = dict(topic_id=key, author=author, published_at=published.isoformat(),
                          scraped_at=captured)
            if pos == "1":
                topic = dict(type="topic", source="discuss.python.org", url=url,
                             title=pick(soup, "#topic-title h1") or title, **common)
            else:
                cid = f"{SOURCE}_c_{number}_{pos}"
                likes = pick(post, ':scope > meta[itemprop="upvoteCount"]', "content")
                posts[cid] = dict(type="comment", comment_id=cid, parent_id=None,
                                  text=body.get_text().strip(),
                                  likes=int(likes) if likes and likes.isdecimal() else None,
                                  dislikes=None, **common)
        next_link = pick(soup, 'link[rel="next"], a[rel="next"]', "href")
        if not soup.select_one(POST) or (len(seen) > 1 and len(posts) == before):
            raise ValueError(f"Stránka nepřinesla nové příspěvky: {page}")
        page = urljoin(page, next_link) if next_link else None
        if page and (canonical(page) or '').rsplit('/', 1)[-1] != number:
            raise ValueError(f"Odkaz Další nevede do téhož vlákna: {page}")
    if topic is None:
        raise ValueError(f"Chybí úvodní příspěvek: {url}")
    return topic, list(posts.values())


def append_topic(root, topic, comments, suffix):
    dt = stamp(topic["published_at"])
    path = root / SOURCE / dt.strftime("%Y") / dt.strftime("%m")
    path.mkdir(parents=True, exist_ok=True)
    path /= f"{SOURCE}-{dt:%y%m%d}-{suffix}.jsonl"
    existing = []
    if path.exists():
        with path.open(encoding="utf-8") as f:
            existing = [json.loads(line) for line in f]
        if existing and (existing[0].get("type") != "topic" or
                         existing[0].get("topic_id") != topic["topic_id"]):
            raise ValueError(f"Nesouhlasí hlavička souboru: {path}")
    known = {item.get("comment_id") for item in existing}
    new = [c for c in comments if c["comment_id"] not in known]
    rows = new if existing else [topic, *new]
    if rows:
        with path.open("a", encoding="utf-8") as f:
            f.write("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in rows))
    return len(new)


def run(args):
    state_file = args.root / "state.json"
    state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}
    processed = set(state.get("processed_topics", []))
    urls = state.get("topic_urls", {})
    cutoff = now() - timedelta(hours=args.active_hours)
    web = Web()
    try:
        topics = discover(web.soup(CATEGORY))
        for number, (url, title, activity) in list(topics.items())[:args.limit]:
            # Zachová původní URL a hash, i když se později změní slug.
            identity_url = urls.get(number, url)
            suffix = hashlib.md5(identity_url.encode("utf-8")).hexdigest()[-8:]
            key = f"{SOURCE}_{suffix}"
            try:
                active = stamp(activity)
            except ValueError:
                active = None
            # Pokud HTML neposkytuje čas aktivity, téma znovu zkontrolujeme.
            if key in processed and active and active < cutoff:
                continue
            try:
                topic, comments = read_topic(web, url, number, title, key, args.max_pages)
                count = append_topic(args.root, topic, comments, suffix)
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code in (403, 429):
                    logging.warning("Server omezil přístup; ukončuji tento cyklus.")
                    break
                logging.warning("%s: %s", url, exc)
                continue
            except (requests.RequestException, ValueError, OSError) as exc:
                logging.warning("%s: %s", url, exc)
                continue
            processed.add(key)
            urls[number] = identity_url
            logging.info("%s: %d nových komentářů", key, count)
        data = dict(last_run=now().isoformat(), processed_topics=sorted(processed), topic_urls=urls)
        tmp = state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(state_file)
    finally:
        web.session.close()


def main():
    parser = argparse.ArgumentParser(description="Statická extrakce diskusí Python Help.")
    parser.add_argument("root", type=Path, help="Kořen dat a souboru state.json")
    parser.add_argument("--watch", action="store_true", help="Opakovat každou hodinu")
    parser.add_argument("--limit", type=int, default=20, help="Maximální počet témat z první stránky")
    parser.add_argument("--max-pages", type=int, default=30)
    parser.add_argument("--active-hours", type=int, default=24)
    args = parser.parse_args()
    if min(args.limit, args.max_pages, args.active_hours) < 1:
        parser.error("Číselné parametry musí být kladné.")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args.root.mkdir(parents=True, exist_ok=True)
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
        time.sleep(max(0, 3600 - (time.monotonic() - started)))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
