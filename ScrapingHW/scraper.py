#!/usr/bin/env python3
"""Univerzální scraper diskusních vláken do JSONL (projekt DEX-C-826).

Skript není svázaný s jedním webem: všechny selektory a adresy jsou v konfiguraci
(scraper.json). Když konfigurace chybí, spustí se průvodce, který se zeptá na adresu,
zkusí sám najít selektory a nechá je zkontrolovat na živých datech.

Rychlý start
------------
    python -m pip install requests beautifulsoup4
    python scraper.py                  # průvodce nastavením + ukázkový test
    python scraper.py --run            # jeden ostrý běh
    python scraper.py --run --watch    # opakovat každou hodinu
    python scraper.py --check          # kontrola datového modelu v JSONL
    python scraper.py --setup          # změnit nastavení (nabídne současné hodnoty)

Užitečné přepínače
------------------
    --config FILE   jiný soubor konfigurace (výchozí scraper.json)
    --root DIR      jiný kořen dat (přepíše hodnotu z konfigurace)
    --limit N       max. témat na jeden běh (0 = bez limitu)
    --max-pages N   max. stránek jednoho vlákna (0 = bez limitu)
    --active-hours N  okno aktivity tématu
    --preset NAME   předvyplnit nastavení hotovým profilem (discourse)
    --yes           přijmout všechny návrhy bez ptání (hodí se pro testování)
    --test          jen vypsat, co by se uložilo, a nic nezapisovat

Struktura výstupu
-----------------
    <root>/<zdroj>/<rok>/<měsíc>/<zdroj>-<YYMMDD>-<hash8>.jsonl
První řádek je téma (type=topic), další řádky komentáře (type=comment).
Nové komentáře se pouze připojují na konec souboru.

Poznámky k datovému modelu
--------------------------
- Datum v cestě i názvu souboru je datum publikace tématu, ne datum stažení.
  U data stažení by každý den vznikl jiný soubor a připojování by ztratilo smysl.
- topic_id = <zdroj>_<8 znaků MD5 z URL tématu>.
- comment_id = <zdroj>_c_<nativní ID>, pokud ho web má; jinak 8 znaků MD5
  z (autor + čas + text), přesně jak žádá zadání.
- parent_id zůstává null, pokud web vztah neposkytuje. Nevymýšlí se.
- likes/dislikes jsou null, pokud je web v HTML nenabízí.
- Model je append-only: editace a smazání příspěvků se nepřenášejí.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from itertools import count
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup, NavigableString

CONFIG_NAME = "scraper.json"
MIN_TIME = datetime.min.replace(tzinfo=timezone.utc)
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})

TIME_FORMATS = [
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%d.%m.%Y",
    "%d. %m. %Y %H:%M",
    "%d. %m. %Y",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%d/%m/%Y %H:%M",
    "%B %d, %Y %H:%M",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d. %B %Y %H:%M",
    "%d. %B %Y",
]

# Výchozí hodnoty. Klíč, který tu není, se do konfigurace neukládá.
DEFAULTS = {
    "base_url": "",
    "allowed_hosts": [],
    "source": "",
    "domain": "",
    "root": "data",
    "user_agent": "SchoolScraper/1.0",
    # seznam témat
    "listing_url": "",
    "list_item_selector": "",
    "list_link_selector": "a",
    "list_activity_selector": "",
    "list_activity_attr": "datetime",
    # vlákno
    "post_selector": "",
    "post_id_attr": "id",
    "post_id_regex": r"(\d+)(?!.*\d)",
    "native_id_template": "{topic}_{id}",
    "topic_from": "first_post",
    "topic_title_selector": "h1",
    "topic_selector": "",
    "topic_author_selector": "",
    "topic_time_selector": "",
    "topic_time_attr": "datetime",
    "author_selector": "",
    "time_selector": "",
    "time_attr": "datetime",
    "text_selector": "",
    "text_separator": "\n",
    "likes_selector": "",
    "likes_attr": "",
    "parent_selector": "",
    "parent_regex": r"(?:post[-_/])?(\d+)",
    "next_selector": 'link[rel="next"], a[rel="next"]',
    "page_url_template": "",
    # chování
    "time_formats": TIME_FORMATS,
    "timezone": "Europe/Prague",
    "delay": 2.0,
    "timeout": 25,
    "retries": 3,
    "limit": 20,
    "max_pages": 30,
    "active_hours": 24,
    "keep_query": False,
    "store_unparsed_time": True,
}

PRESETS = {
    "discourse": {
        "base_url": "https://discuss.python.org",
        "allowed_hosts": ["discuss.python.org"],
        "source": "python",
        "domain": "discuss.python.org",
        "listing_url": "https://discuss.python.org/c/help/7",
        "list_item_selector": "tr.topic-list-item",
        "list_link_selector": 'a.raw-topic-link, a.title, a[itemprop="url"]',
        "list_activity_selector": "",
        "post_selector": 'div.topic-body.crawler-post[id^="post_"]',
        "post_id_attr": "id",
        "post_id_regex": r"post_(\d+)",
        "native_id_template": "{topic}_{id}",
        "topic_from": "first_post",
        "topic_title_selector": "#topic-title h1, h1",
        "author_selector": '.creator [itemprop="name"]',
        "time_selector": "time.post-time",
        "time_attr": "datetime",
        "text_selector": '.post[itemprop="text"]',
        "likes_selector": ':scope > meta[itemprop="upvoteCount"]',
        "likes_attr": "content",
        "parent_selector": "",
        "next_selector": 'link[rel="next"], a[rel="next"]',
        "user_agent": "PythonForumSchoolScraper/1.0",
        "timezone": "UTC",
    }
}


class LockBusy(RuntimeError):
    """Nad stejnou složkou už běží jiná instance scraperu."""


# --------------------------------------------------------------------------- čas

def now() -> datetime:
    return datetime.now(timezone.utc)


def md5_8(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[-8:]


def local_tz(cfg: dict):
    name = (cfg.get("timezone") or "UTC").strip()
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name)
    except Exception:
        logging.warning(
            "Časovou zónu %s nelze načíst (na Windows pomůže 'pip install tzdata'); "
            "používám pevný posun +01:00.", name,
        )
        return timezone(timedelta(hours=1))


def parse_time(value, cfg: dict):
    """Vrátí čas s časovou zónou, nebo None. Podporuje ISO 8601 i běžné české formáty."""
    if not value:
        return None
    text = " ".join(str(value).split())
    if not text:
        return None
    tz = local_tz(cfg)
    iso = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso)
        return dt if dt.tzinfo else dt.replace(tzinfo=tz)
    except ValueError:
        pass
    if re.fullmatch(r"\d{9,11}", text):  # unixový čas v sekundách
        return datetime.fromtimestamp(int(text), tz=timezone.utc)
    for fmt in cfg.get("time_formats") or TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=tz)
        except ValueError:
            continue
    # české textové měsíce: "21. října 2026", "21. října 2026 14:30"
    m = re.fullmatch(
        r"(\d{1,2})\.?\s*([A-Za-zÁ-Žá-ž]+)\s*(\d{4})"
        r"(?:,?\s*(?:v\s*)?(\d{1,2})[:.](\d{2}))?",
        text,
    )
    if m:
        month = CZECH_MONTHS.get(m.group(2).lower())
        if month:
            return datetime(
                int(m.group(3)), month, int(m.group(1)),
                int(m.group(4) or 0), int(m.group(5) or 0), tzinfo=tz,
            )
    return None


CZECH_MONTHS = {
    "ledna": 1, "leden": 1, "února": 2, "unora": 2, "únor": 2, "unor": 2,
    "března": 3, "brezna": 3, "březen": 3, "brezen": 3,
    "dubna": 4, "duben": 4, "května": 5, "kvetna": 5, "květen": 5, "kveten": 5,
    "června": 6, "cervna": 6, "červen": 6, "cerven": 6,
    "července": 7, "cervence": 7, "červenec": 7, "cervenec": 7,
    "srpna": 8, "srpen": 8, "září": 9, "zari": 9,
    "října": 10, "rijna": 10, "říjen": 10, "rijen": 10,
    "listopadu": 11, "listopad": 11, "prosince": 12, "prosinec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}


# ------------------------------------------------------------------------- URL

def canonical_url(cfg: dict, url: str) -> str:
    """Odstraní fragment, volitelně query a koncové lomítko, aby měl odkaz stabilní podobu."""
    u = urlsplit(url)
    path = re.sub(r"/+$", "", u.path) or "/"
    query = u.query if cfg.get("keep_query") else ""
    return urlunsplit((u.scheme, u.netloc.lower(), path, query, ""))


def host_of(url: str) -> str:
    return urlsplit(url).netloc.lower()


def is_loopback(url: str) -> bool:
    host = urlsplit(url).hostname or ""
    return host in ("localhost", "127.0.0.1", "::1")


# ------------------------------------------------------------------------ Web

class Web:
    """HTTP klient: robots.txt, zdvořilá prodleva, omezené opakování, přesměrování."""

    MAX_HOPS = 5

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": cfg.get("user_agent") or "SchoolScraper/1.0",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "cs,en;q=0.8",
        })
        self.hosts = {h.lower() for h in (cfg.get("allowed_hosts") or [])} or {host_of(cfg["base_url"])}
        self.robot = RobotFileParser()
        self.robot.parse([])  # výchozí stav: procházení povoleno, dokud robots neřekne jinak
        self.deny_all = False
        self.delay = float(cfg.get("delay") or 2.0)
        self.timeout = float(cfg.get("timeout") or 25)
        self.retries = max(1, int(cfg.get("retries") or 3))
        self.last = 0.0
        self._load_robots()

    def _load_robots(self) -> None:
        url = urljoin(self.cfg["base_url"], "/robots.txt")
        try:
            response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
        except requests.RequestException as exc:
            logging.warning("robots.txt se nepodařilo načíst (%s), pokračuji opatrně.", exc)
            return
        if response.status_code in (401, 403):
            logging.error("robots.txt vrací %s – web procházení odmítá.", response.status_code)
            self.deny_all = True
            return
        if response.status_code >= 500:
            logging.warning("robots.txt vrací %s, pokračuji opatrně.", response.status_code)
            return
        if response.status_code >= 400:
            logging.info("robots.txt neexistuje (%s) – procházení není omezeno.", response.status_code)
            return
        self.robot.parse(response.text.splitlines())
        robot_delay = self.robot.crawl_delay(self.session.headers["User-Agent"]) or self.robot.crawl_delay("*")
        if robot_delay:
            self.delay = max(self.delay, float(robot_delay))

    def _check(self, url: str) -> None:
        u = urlsplit(url)
        if u.scheme not in ("http", "https"):
            raise ValueError(f"Nepodporovaná adresa: {url}")
        if u.scheme == "http" and not is_loopback(url):
            raise ValueError(f"HTTP povoluji jen pro localhost, ne pro {url}")
        if u.netloc.lower() not in self.hosts:
            raise ValueError(f"Cizí adresa mimo povolené domény: {url}")
        if self.deny_all:
            raise ValueError("robots.txt procházení zakazuje.")
        if not self.robot.can_fetch(self.session.headers["User-Agent"], url):
            raise ValueError(f"Cesta zakázaná v robots.txt: {url}")

    def _wait(self) -> None:
        time.sleep(max(0.0, self.delay - (time.monotonic() - self.last)))
        self.last = time.monotonic()

    def _retry_after(self, response, default: float) -> float:
        raw = (response.headers.get("Retry-After") or "").strip()
        if raw.isdigit():
            return float(raw)
        if raw:
            try:
                return max(0.0, (parsedate_to_datetime(raw) - now()).total_seconds())
            except (TypeError, ValueError):
                pass
        return default

    def _request(self, url: str):
        response = None
        for attempt in range(1, self.retries + 1):
            self._wait()
            try:
                response = self.session.get(url, timeout=self.timeout, allow_redirects=False)
            except requests.RequestException:
                if attempt == self.retries:
                    raise
                time.sleep(min(30.0, 5.0 * 2 ** (attempt - 1)))
                continue
            if response.status_code in RETRY_STATUS and attempt < self.retries:
                wait = min(300.0, self._retry_after(response, 5.0 * 2 ** (attempt - 1)))
                logging.warning("HTTP %s u %s, čekám %.0f s", response.status_code, url, wait)
                time.sleep(wait)
                continue
            return response
        return response

    def response(self, url: str, check: bool = True):
        for _ in range(self.MAX_HOPS):
            if check:
                self._check(url)
            response = self._request(url)
            if response.is_redirect:
                target = urljoin(url, response.headers.get("Location", ""))
                self._check(target)
                url = target
                continue
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError(f"Neočekávaný stav HTTP {response.status_code}: {url}")
            return response
        raise ValueError(f"Příliš mnoho přesměrování: {url}")

    def fetch(self, url: str, check: bool = True) -> str:
        return self.response(url, check).text

    def soup(self, url: str, check: bool = True) -> BeautifulSoup:
        # Předáváme bajty, aby si BeautifulSoup sám přečetl <meta charset>.
        # Jinak by se české weby bez charset v hlavičce rozsypaly do mojibake.
        return BeautifulSoup(self.response(url, check).content, "html.parser")


# ------------------------------------------------------------ extrakce polí

BLOCK_TAGS = frozenset({
    "address", "article", "aside", "blockquote", "br", "dd", "details", "div", "dl",
    "dt", "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4",
    "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre", "section",
    "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
})


def clean_text(node, separator: str = "\n") -> str:
    """Text uzlu se zlomy jen mezi bloky – odstavce a bloky kódu zůstanou zachované."""
    if node is None:
        return ""
    if isinstance(node, str):
        return " ".join(node.split())
    parts = []
    for element in node.descendants:
        if isinstance(element, NavigableString):
            parts.append(str(element))
        elif getattr(element, "name", None) in BLOCK_TAGS:
            parts.append(separator)
    text = "".join(parts)
    text = text.replace("\u200b", "").replace("\xa0", " ")
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    # Vlastní oddělovač (např. " | ") nesmí zůstat na začátku ani na konci textu.
    sep = separator.strip()
    if sep and sep != "\n":
        while text.startswith(sep):
            text = text[len(sep):].lstrip()
        while text.endswith(sep):
            text = text[:-len(sep)].rstrip()
    return text


def pick(node, selector: str, attr: str | None = None):
    """Vrátí atribut nebo text prvního nalezeného uzlu; None když selector nesedí."""
    if not selector:
        return None
    try:
        found = node.select_one(selector)
    except Exception as exc:  # neplatný CSS selektor
        raise ValueError(f"Neplatný selektor {selector!r}: {exc}") from exc
    if found is None:
        return None
    if attr:
        value = found.get(attr)
        if value is None and attr != "text":
            return None
        return value if value is not None else clean_text(found)
    return clean_text(found)


def first_int(value):
    if value is None:
        return None
    m = re.search(r"-?\d+", str(value).replace(" ", "").replace("\u00a0", ""))
    return int(m.group(0)) if m else None


def extract_post_id(cfg: dict, block) -> str | None:
    attr = cfg.get("post_id_attr") or "id"
    raw = block.get(attr) if attr else None
    if raw is None and attr != "id":
        raw = block.get("id")
    if not raw:
        return None
    pattern = cfg.get("post_id_regex")
    if pattern:
        m = re.search(pattern, str(raw))
        return m.group(1) if m and m.groups() else (m.group(0) if m else None)
    return str(raw)


def comment_id_for(cfg: dict, topic_ref: str, post: dict) -> str:
    native = post.get("native_id")
    if native:
        template = cfg.get("native_id_template") or "{id}"
        try:
            body = template.format(topic=topic_ref, id=native)
        except (KeyError, IndexError):
            body = str(native)
        return f"{cfg['source']}_c_{body}"
    basis = f"{post.get('author') or ''}|{post.get('published_at') or post.get('published_raw') or ''}|{post.get('text') or ''}"
    return f"{cfg['source']}_c_{md5_8(basis)}"


def read_time(block, selector: str, attr: str | None):
    """Přečte čas ve třech krocích: atribut -> text uzlu -> selektor bez podmínek na atributy.

    Třetí krok řeší weby, kde část stránek má <time datetime="..."> a část jen
    <time>13. listopadu 2026</time>. Bez něj by takové vlákno skončilo chybou.
    """
    if not selector:
        return None
    value = pick(block, selector, attr or None)
    if value is None:
        value = pick(block, selector)
    if value is None and "[" in selector:
        loose = re.sub(r"\[[^\]]*\]", "", selector).strip()
        if loose and loose != selector:
            value = pick(block, loose)
    return value


def make_topic(cfg: dict, url: str, title: str | None, author: str | None,
               published: str | None, captured: str) -> dict:
    """Sestaví záznam tématu ve stejném pořadí polí jako v zadání."""
    return {
        "type": "topic",
        "topic_id": f"{cfg['source']}_{md5_8(url)}",
        "source": cfg["domain"] or host_of(url),
        "url": url,
        "title": title,
        "author": author,
        "published_at": published,
        "scraped_at": captured,
    }


def topic_from_header(cfg: dict, url: str, title: str | None, hint_title: str | None,
                     topic_block, first_post: dict, captured: str) -> dict:
    """Téma z hlavičky mimo seznam příspěvků – volba topic_from=header.

    Hodí se na weby, kde nadpis, autor a datum tématu stojí ve vlastním bloku
    (např. <div class="thread-head">) a první příspěvek je až pod ním.
    """
    if topic_block is None:
        raise ValueError(
            "topic_from=header vyžaduje topic_selector (blok s hlavičkou tématu)."
        )
    raw_time = read_time(topic_block, cfg.get("topic_time_selector") or "", cfg.get("topic_time_attr"))
    parsed = parse_time(raw_time, cfg)
    published = parsed.isoformat() if parsed else None
    if published is None:
        # Nouzově datum prvního příspěvku – pořád lepší než záznam zahodit.
        published = first_post.get("published_at")
    if published is None:
        raise ValueError(
            f"Nepodařilo se přečíst čas tématu ({raw_time!r}). "
            "Upravte topic_time_selector, topic_time_attr nebo time_formats."
        )
    author = pick(topic_block, cfg["topic_author_selector"]) if cfg.get("topic_author_selector") else None
    author = author or first_post.get("author")
    if not title and cfg.get("topic_title_selector"):
        title = pick(topic_block, cfg["topic_title_selector"])
    return make_topic(cfg, url, title or hint_title or clean_text(topic_block)[:120], author, published, captured)


def extract_post(cfg: dict, block, soup) -> dict:
    """Vytáhne z jednoho bloku pole společná pro téma i komentář."""
    raw_time = read_time(block, cfg.get("time_selector") or "", cfg.get("time_attr"))
    published = parse_time(raw_time, cfg)
    text = ""
    if cfg.get("text_selector"):
        try:
            text_node = block.select_one(cfg["text_selector"])
        except Exception as exc:  # neplatný CSS selektor
            raise ValueError(f"Neplatný selektor {cfg['text_selector']!r}: {exc}") from exc
        text = clean_text(text_node, cfg.get("text_separator") or "\n") if text_node is not None else ""
    likes = None
    if cfg.get("likes_selector"):
        raw_likes = pick(block, cfg["likes_selector"], cfg.get("likes_attr") or None)
        likes = first_int(raw_likes)
    parent_native = None
    if cfg.get("parent_selector"):
        raw_parent = pick(block, cfg["parent_selector"], None)
        if raw_parent:
            m = re.search(cfg.get("parent_regex") or r"(\d+)", raw_parent)
            parent_native = m.group(1) if m and m.groups() else None
    return {
        "native_id": extract_post_id(cfg, block),
        "parent_native": parent_native,
        "author": pick(block, cfg.get("author_selector")) if cfg.get("author_selector") else None,
        "published_at": published.isoformat() if published else None,
        "published_raw": None if published else (raw_time or None),
        "text": text,
        "likes": likes,
    }


# ------------------------------------------------------------------ stahování

def discover(cfg: dict, web: Web, listing_url: str) -> dict:
    """Vrátí {kanonická URL: {'url', 'title', 'activity'}} pro témata na seznamu."""
    soup = web.soup(listing_url)
    containers = soup.select(cfg["list_item_selector"]) if cfg.get("list_item_selector") else [soup]
    if not containers:
        raise ValueError(
            f"Selektor seznamu {cfg.get('list_item_selector')!r} nic nenašel "
            "(změnil se web, nebo je potřeba upravit nastavení)."
        )
    items = {}
    for node in containers:
        links = node.select(cfg.get("list_link_selector") or "a")
        for link in links:
            href = link.get("href")
            if not href:
                continue
            url = canonical_url(cfg, urljoin(listing_url, href))
            if host_of(url) not in web.hosts:
                continue
            items.setdefault(url, {
                "url": url,
                "title": clean_text(link) or None,
                "activity": parse_time(
                    pick(node, cfg["list_activity_selector"], cfg.get("list_activity_attr") or None)
                    if cfg.get("list_activity_selector") else None,
                    cfg,
                ),
            })
            break
    if not items:
        raise ValueError("Na stránce seznamu nebyly nalezeny žádné odkazy na témata.")
    return items


def read_topic(cfg: dict, web: Web, url: str, hint_title: str | None, max_pages: int):
    """Stáhne vlákno. Vrací (téma, komentáře, complete, čas posledního příspěvku)."""
    page = url
    seen_pages: set[str] = set()
    posts: dict[str, dict] = {}
    topic = None
    topic_ref = md5_8(canonical_url(cfg, url))
    captured = now().isoformat()
    last_post = None
    complete = True

    for page_no in count(1):
        if page in seen_pages:
            raise ValueError(f"Smyčka ve stránkování: {page}")
        if max_pages and len(seen_pages) >= max_pages:
            logging.warning("Překročen limit %d stránek u %s, ukládám částečná data.", max_pages, url)
            complete = False
            break
        seen_pages.add(page)
        soup = web.soup(page)
        blocks = soup.select(cfg["post_selector"]) if cfg.get("post_selector") else []
        if not blocks:
            raise ValueError(f"Selektor příspěvků {cfg.get('post_selector')!r} nic nenašel na {page}")

        title = None
        if cfg.get("topic_title_selector"):
            title = pick(soup, cfg["topic_title_selector"])
        # Některé weby mají hlavičku tématu mimo seznam příspěvků (nadpis, autor, datum).
        topic_block = None
        if cfg.get("topic_selector"):
            try:
                topic_block = soup.select_one(cfg["topic_selector"])
            except Exception as exc:  # neplatný CSS selektor
                raise ValueError(f"Neplatný selektor {cfg['topic_selector']!r}: {exc}") from exc

        mode = cfg.get("topic_from") or "first_post"
        for index, block in enumerate(blocks):
            data = extract_post(cfg, block, soup)
            if topic is None and page_no == 1:
                if mode == "header":
                    # Téma je v hlavičce, tento příspěvek se uloží jako běžný komentář.
                    topic = topic_from_header(cfg, url, title, hint_title, topic_block, data, captured)
                    last_post = datetime.fromisoformat(topic["published_at"])
                else:
                    published = data["published_at"]
                    author = data["author"]
                    if topic_block is not None:
                        if cfg.get("topic_author_selector"):
                            author = pick(topic_block, cfg["topic_author_selector"]) or author
                        if cfg.get("topic_time_selector"):
                            raw_topic_time = read_time(
                                topic_block, cfg["topic_time_selector"], cfg.get("topic_time_attr")
                            )
                            parsed_topic_time = parse_time(raw_topic_time, cfg)
                            if parsed_topic_time is not None:
                                published = parsed_topic_time.isoformat()
                    if published is None:
                        raise ValueError(
                            f"Nepodařilo se přečíst čas tématu ({data['published_raw']!r}). "
                            "Upravte time_selector, time_attr nebo time_formats."
                        )
                    topic = make_topic(
                        cfg, url, title or hint_title or clean_text(block)[:120], author, published, captured
                    )
                    last_post = datetime.fromisoformat(published)
                    continue
            if not data["text"]:
                logging.warning("Přeskakuji příspěvek bez textu na %s", page)
                continue
            cid = comment_id_for(cfg, topic_ref, data)
            if cid in posts:
                # Nativní ID se na stránce opakuje (např. číslování v rámci stránky);
                # přejdeme na hash z autora, času a textu, aby se příspěvky nepřebily.
                cid = comment_id_for(cfg, topic_ref, {**data, "native_id": None})
            record = {
                "type": "comment",
                "comment_id": cid,
                "topic_id": f"{cfg['source']}_{md5_8(url)}",
                "parent_id": None,
                "author": data["author"],
                "published_at": data["published_at"],
                "scraped_at": captured,
                "text": data["text"],
                "likes": data["likes"],
                "dislikes": None,
            }
            if data["published_at"] is None and cfg.get("store_unparsed_time", True):
                record["published_at_raw"] = data["published_raw"]
            if data["parent_native"]:
                parent = comment_id_for(cfg, topic_ref, {"native_id": data["parent_native"]})
                if parent != cid:
                    record["parent_id"] = parent
            posts.setdefault(cid, record)
            if data["published_at"]:
                stamp = datetime.fromisoformat(data["published_at"])
                if last_post is None or stamp > last_post:
                    last_post = stamp

        next_href = pick(soup, cfg.get("next_selector") or "", "href") if cfg.get("next_selector") else None
        if next_href:
            # U stránkování se query nesmí zahodit (často nese ?page=2).
            target = urlsplit(urljoin(page, next_href))
            page = urlunsplit((target.scheme, target.netloc.lower(), target.path, target.query, ""))
        elif cfg.get("page_url_template") and len(blocks) >= 2:
            page = cfg["page_url_template"].format(url=url, page=page_no + 1)
        else:
            page = None
        if page and page in seen_pages:
            page = None
        if not page:
            break

    if topic is None:
        raise ValueError(f"Chybí úvodní příspěvek tématu: {url}")
    if last_post is None:
        last_post = datetime.fromisoformat(topic["published_at"])
    return topic, list(posts.values()), complete, last_post


def append_topic(cfg: dict, root: Path, topic: dict, comments: list[dict]) -> tuple[int, int]:
    """Připojí nové komentáře. Vrací (počet nových, celkový počet komentářů)."""
    dt = datetime.fromisoformat(topic["published_at"])
    directory = root / cfg["source"] / f"{dt:%Y}" / f"{dt:%m}"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{cfg['source']}-{dt:%y%m%d}-{md5_8(topic['url'])}.jsonl"

    existing: list[dict] = []
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    existing.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Poškozený JSONL {path}:{lineno}: {exc.msg}") from exc
        if not existing or existing[0].get("type") != "topic" or existing[0].get("topic_id") != topic["topic_id"]:
            raise ValueError(f"Nesouhlasí hlavička souboru: {path}")

    known = {r.get("comment_id") for r in existing if r.get("type") == "comment"}
    new = [c for c in comments if c["comment_id"] not in known]
    rows = new if existing else [topic, *new]
    with path.open("a", encoding="utf-8") as f:
        if rows:
            f.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        f.flush()
        os.fsync(f.fileno())
    return len(new), len(known) + len(new)


# -------------------------------------------------------------------- stav

def load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("kořen není objekt")
        return data
    except (OSError, ValueError) as exc:
        broken = path.with_name(f"state.corrupt-{now():%Y%m%d%H%M%S}.json")
        logging.error("state.json nelze načíst (%s), odkládám do %s", exc, broken.name)
        with contextlib.suppress(OSError):
            path.replace(broken)
        return {}


def save_state(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


@contextlib.contextmanager
def single_instance(path: Path):
    """Zámek, aby nad jednou složkou neběžely dvě instance (fcntl / msvcrt)."""
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


# --------------------------------------------------------------- jeden běh

def run(cfg: dict, args) -> None:
    root = Path(args.root or cfg.get("root") or "data")
    root.mkdir(parents=True, exist_ok=True)
    state_file = root / "state.json"
    state = load_state(state_file)
    web = Web(cfg)
    processed = set(state.get("processed_topics", []))
    learned = dict(state.get("last_activity", {}))
    urls = dict(state.get("topic_urls", {}))
    cutoff = now() - timedelta(hours=int(cfg["active_hours"]))
    scraped = 0
    try:
        items = discover(cfg, web, cfg["listing_url"])
        candidates = []
        for url, meta in items.items():
            identity = urls.get(url, url)
            key = f"{cfg['source']}_{md5_8(identity)}"
            activity = meta.get("activity")
            seen_at = parse_time(learned.get(key), cfg) or MIN_TIME
            active = (activity is not None and activity >= cutoff) or (seen_at >= cutoff)
            if key in processed and not active:
                logging.debug("%s: neaktivní, přeskakuji", key)
                continue
            candidates.append((key in processed, seen_at, url, key, identity, meta))
        # Nejdřív nezpracovaná témata, pak ta nejdéle nekontrolovaná.
        candidates.sort(key=lambda c: (c[0], c[1], c[2]))

        for _, _, url, key, identity, meta in candidates:
            if cfg["limit"] and scraped >= int(cfg["limit"]):
                break
            try:
                topic, comments, complete, last = read_topic(
                    cfg, web, url, meta.get("title"), int(cfg["max_pages"])
                )
                new, total = append_topic(cfg, root, topic, comments)
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
            urls[url] = identity
            if complete:
                processed.add(key)
            learned[key] = last.isoformat()
            logging.info("%s: +%d komentářů (celkem %d)%s", key, new, total, "" if complete else " [neúplné]")

        save_state(state_file, {
            "last_run": now().isoformat(),
            "processed_topics": sorted(processed),
            "topic_urls": dict(sorted(urls.items())),
            "last_activity": dict(sorted(learned.items())),
        })
    finally:
        web.session.close()


def loop(cfg: dict, args) -> int:
    while True:
        started = time.monotonic()
        try:
            run(cfg, args)
        except (requests.RequestException, ValueError, OSError) as exc:
            logging.error("Cyklus selhal: %s", exc)
            if not args.watch:
                return 1
        if not args.watch:
            return 0
        time.sleep(max(0.0, 3600 - (time.monotonic() - started)))


def dry_run(cfg: dict, args) -> int:
    """Vypíše prvních pár záznamů, které by se uložily. Nic nezapisuje."""
    web = Web(cfg)
    try:
        items = discover(cfg, web, cfg["listing_url"])
        print(f"\nNalezeno témat na seznamu: {len(items)}")
        for i, (url, meta) in enumerate(items.items(), 1):
            print(f"  {i}. {meta.get('title') or '(bez titulku)'}\n     {url}")
        url = next(iter(items))
        print(f"\nZkouším stáhnout první téma: {url}\n")
        topic, comments, complete, _ = read_topic(cfg, web, url, items[url].get("title"), int(cfg["max_pages"]))
    except (requests.RequestException, ValueError, OSError) as exc:
        print(f"\nCHYBA: {exc}")
        print("Zkontrolujte selektory (--setup) nebo zda web nevyžaduje JavaScript.")
        return 1
    finally:
        web.session.close()
    print(json.dumps(topic, ensure_ascii=False, indent=2))
    for record in comments[:3]:
        print(json.dumps(record, ensure_ascii=False, indent=2))
    if len(comments) > 3:
        print(f"... a dalších {len(comments) - 3} komentářů")
    missing = sum(1 for c in comments if c.get("published_at") is None)
    print(f"\nCelkem komentářů: {len(comments)}, bez přečteného času: {missing}, kompletní: {complete}")
    if not comments:
        print("VAROVÁNÍ: nebyly nalezeny žádné komentáře – zkontrolujte post_selector a text_selector.")
    if missing:
        print("VAROVÁNÍ: u části příspěvků se nepodařilo přečíst čas; upravte time_selector/time_formats.")
    return 0 if comments else 1


# ---------------------------------------------------------------- validátor

def validate(cfg: dict, root: Path) -> int:
    files = sorted(root.rglob("*.jsonl"))
    if not files:
        print(f"Nenalezeny žádné .jsonl soubory v {root}.")
        return 1
    problems, warnings = [], []
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
        suffix = md5_8(url)
        if topic.get("topic_id") != f"{cfg['source']}_{suffix}":
            problems.append(f"{rel}: topic_id neodpovídá MD5 z url")
        if cfg.get("domain") and topic.get("source") != cfg["domain"]:
            problems.append(f"{rel}: source != {cfg['domain']}")
        for field in ("url", "title", "published_at", "scraped_at"):
            if not topic.get(field):
                problems.append(f"{rel}: téma nemá pole {field}")
        dt = parse_time(topic.get("published_at"), cfg)
        if dt is None:
            problems.append(f"{rel}: published_at není platný čas")
        elif len(rel.parts) == 4:
            source, year, month, name = rel.parts
            if source != cfg["source"]:
                problems.append(f"{rel}: adresář zdroje != {cfg['source']}")
            if (year, month) != (f"{dt:%Y}", f"{dt:%m}"):
                problems.append(f"{rel}: adresář roku/měsíce neodpovídá published_at")
            if name != f"{cfg['source']}-{dt:%y%m%d}-{suffix}.jsonl":
                problems.append(f"{rel}: název souboru neodpovídá datu a hashi")
        else:
            problems.append(f"{rel}: neočekávaná hloubka cesty")
        ids = set()
        for rec in records[1:]:
            if rec.get("type") != "comment":
                problems.append(f"{rel}: záznam typu {rec.get('type')!r} mezi komentáři")
                continue
            for field in ("comment_id", "topic_id", "author", "published_at",
                          "scraped_at", "text", "likes", "dislikes"):
                if field not in rec:
                    problems.append(f"{rel}: komentář nemá pole {field}")
            if rec.get("topic_id") != topic.get("topic_id"):
                problems.append(f"{rel}: komentář {rec.get('comment_id')} má cizí topic_id")
            if not str(rec.get("comment_id", "")).startswith(f"{cfg['source']}_c_"):
                problems.append(f"{rel}: comment_id nemá prefix {cfg['source']}_c_")
            if rec.get("comment_id") in ids:
                problems.append(f"{rel}: duplicitní comment_id {rec.get('comment_id')}")
            ids.add(rec.get("comment_id"))
            if parse_time(rec.get("published_at"), cfg) is None:
                if rec.get("published_at_raw"):
                    warnings.append(f"{rel}: {rec.get('comment_id')} má nepřečtený čas {rec['published_at_raw']!r}")
                else:
                    problems.append(f"{rel}: komentář {rec.get('comment_id')} nemá platný čas")
            if parse_time(rec.get("scraped_at"), cfg) is None:
                problems.append(f"{rel}: komentář {rec.get('comment_id')} nemá platný scraped_at")
            if not isinstance(rec.get("text"), str):
                problems.append(f"{rel}: komentář {rec.get('comment_id')} nemá text")
        for rec in records[1:]:
            parent = rec.get("parent_id")
            if parent is not None and parent not in ids:
                warnings.append(f"{rel}: parent_id {parent} není v souboru (rodič na jiné stránce?)")
        comments_total += len(records) - 1

    for problem in problems:
        print(f"CHYBA  {problem}")
    for warning in warnings:
        print(f"VAROVÁNÍ {warning}")
    print(f"Souborů: {len(files)}, komentářů: {comments_total}, chyb: {len(problems)}, varování: {len(warnings)}")
    return 1 if problems else 0


# ------------------------------------------------------------ průvodce

def signature(el) -> str:
    """CSS podpis uzlu: tag + první dvě 'bezpečné' třídy."""
    if el is None or el.name in (None, "body", "html", "[document]"):
        return ""
    classes = [c for c in (el.get("class") or []) if re.fullmatch(r"[A-Za-z][\w-]*", c)]
    return el.name + "".join("." + c for c in classes[:2])


def detect_link_clusters(soup, base: str, allowed: set[str], limit: int = 8) -> list[dict]:
    """Seskupí odkazy podle tvaru cesty a navrhne pro každou skupinu CSS selektor."""
    groups: dict[str, list[str]] = {}
    for a in soup.select("a[href]"):
        url = urljoin(base, a["href"])
        if host_of(url) not in allowed:
            continue
        path = urlsplit(url).path
        if not path or path == "/":
            continue
        pattern = re.sub(r"\d+", "#", path)
        groups.setdefault(pattern, [])
        if url not in groups[pattern]:
            groups[pattern].append(url)
    result = []
    for pattern, urls in groups.items():
        if len(urls) < 3:
            continue
        literal = pattern.split("#", 1)[0]
        literal = literal.rsplit("/", 1)[0] if literal.endswith("/") else literal
        if len(literal) < 2:
            continue
        selector = f'a[href*="{literal}"]'
        try:
            matched = len(soup.select(selector))
        except Exception:
            continue
        if matched < 3:
            continue
        result.append({
            "selector": selector,
            "count": matched,
            "distinct": len(urls),
            "pattern": pattern,
            "sample": urls[0],
        })
    result.sort(key=lambda r: (-r["distinct"], -r["count"]))
    return result[:limit]


def guess_container(soup, link) -> str:
    """Nejbližší předek odkazu, který se na stránce opakuje (typicky řádek tématu)."""
    node = link
    for _ in range(8):
        node = node.parent
        if node is None or node.name in ("body", "html", "[document]"):
            break
        sig = signature(node)
        if not sig:
            continue
        try:
            total = len(soup.select(sig))
        except Exception:
            continue
        if total >= 3:
            return sig
    return ""


def detect_blocks(soup, limit: int = 8) -> list[dict]:
    """Najde opakující se bloky s textem – kandidáty na jeden příspěvek."""
    groups: dict[str, list] = {}
    for el in soup.find_all(True):
        sig = signature(el)
        if not sig or sig.split(".")[0] in ("html", "head", "script", "style", "meta", "link"):
            continue
        text = el.get_text(" ", strip=True)
        if len(text) < 40:
            continue
        groups.setdefault(sig, []).append(el)
    result = []
    for sig, elements in groups.items():
        if not 2 <= len(elements) <= 400:
            continue
        lengths = sorted(len(e.get_text(" ", strip=True)) for e in elements)
        median = lengths[len(lengths) // 2]
        if median < 40:
            continue
        result.append({
            "selector": sig,
            "count": len(elements),
            "median": median,
            "score": len(elements) * min(median, 600),
        })
    result.sort(key=lambda r: -r["score"])
    return result[:limit]


FIELD_HINTS = {
    "author": [
        '.creator [itemprop="name"]', '[itemprop="author"] [itemprop="name"]', '[itemprop="author"]',
        ".author", ".username", ".user-name", ".nick", "a[href*='/u/']", "a[href*='/user']",
        "a[href*='/profil']", ".name",
    ],
    "time": [
        "time[datetime]", "time[data-time]", "time", "[itemprop='datePublished']",
        "[datetime]", ".date", ".time", ".post-time", ".published", ".datum",
    ],
    "text": [
        '[itemprop="text"]', ".post", ".cooked", ".content", ".message", ".text",
        ".body", ".comment-text", ".prispevek", "article", "p",
    ],
    "likes": [
        '[itemprop="upvoteCount"]', ".likes", ".likes-count", ".score", ".votes",
        "[data-likes]", ".rating", ".hlasu",
    ],
    "parent": [
        'a[href*="#post-"]', 'a[href*="/post/"]', ".reply-to", ".in-reply-to",
        "[itemprop='parentItem']", ".quote",
    ],
    "next": [
        'link[rel="next"]', 'a[rel="next"]', ".pagination a.next", "a.next",
        "a[aria-label*='Next']", "a[aria-label*='Další']", ".pager-next a",
    ],
}


def score_field(blocks: list, selector: str, attr: str | None) -> dict:
    """Zjistí, na kolika blocích selektor něco najde, a vrátí ukázku."""
    hits, samples = 0, []
    for block in blocks[:5]:
        try:
            node = block.select_one(selector)
        except Exception:
            return {"selector": selector, "attr": attr, "hits": 0, "sample": None}
        if node is None:
            continue
        value = node.get(attr) if attr else None
        if value is None:
            value = clean_text(node)
        if value:
            hits += 1
            if len(samples) < 2:
                samples.append(str(value)[:60])
    return {"selector": selector, "attr": attr, "hits": hits, "sample": " | ".join(samples) or None}


def suggest_field(blocks: list, field: str) -> dict:
    """Vrátí nejlepší návrh selektoru pro dané pole."""
    best = {"selector": "", "attr": "", "hits": 0, "sample": None}
    for selector in FIELD_HINTS[field]:
        attrs = [None]
        if "[datetime]" in selector:
            attrs = ["datetime"]
        elif "data-time" in selector:
            attrs = ["data-time"]
        elif "upvoteCount" in selector or "[data-likes]" in selector:
            attrs = ["content" if "upvoteCount" in selector else "data-likes", None]
        for attr in attrs:
            result = score_field(blocks, selector, attr)
            if result["hits"] > best["hits"]:
                best = result
    return best


def ask(prompt: str, default: str = "", yes: bool = False) -> str:
    """Zeptá se na hodnotu; Enter = výchozí, --yes = výchozí bez ptání."""
    if yes:
        print(f"{prompt} [{default}] -> {default or '(prázdné)'}")
        return default
    try:
        value = input(f"{prompt} [{default}]: ").strip()
    except EOFError:
        print()
        return default
    return value or default


def ask_int(prompt: str, default: int, yes: bool = False) -> int:
    while True:
        raw = ask(prompt, str(default), yes)
        try:
            return int(raw)
        except ValueError:
            if yes:
                return default
            print("  Zadejte prosím celé číslo.")


def ask_choice(prompt: str, options: list[dict], default: int = 1, yes: bool = False) -> dict | None:
    """Nabídne číslovaný seznam; vrací vybranou položku nebo None pro ruční zadání."""
    if not options:
        return None
    if not yes:
        for i, option in enumerate(options, 1):
            extra = f"  (např. {option['sample']})" if option.get("sample") else ""
            count = option.get("distinct") or option.get("count")
            print(f"  {i}) {option['selector']:<45} {count}× {extra}")
    raw = ask(prompt, str(default), yes)
    if raw.lower() in ("", "0"):
        return options[min(default, len(options)) - 1]
    if raw.lower() in ("n", "ne", "x", "-"):
        return None
    try:
        index = int(raw)
    except ValueError:
        return None
    if 1 <= index <= len(options):
        return options[index - 1]
    return None


def derive_source(url: str) -> tuple[str, str]:
    host = urlsplit(url).hostname or host_of(url)
    try:
        import ipaddress

        ipaddress.ip_address(host)
        return ("localhost" if host in ("127.0.0.1", "::1", "localhost") else "web"), host
    except ValueError:
        pass
    labels = [p for p in host.split(".") if p]
    if labels and labels[0] == "www":
        labels = labels[1:]
    domain = ".".join(labels)
    source = labels[0] if labels else "web"
    return re.sub(r"[^a-z0-9]+", "", source.lower()) or "web", domain


def wizard(config_path: Path, preset: str | None, yes: bool, listing: str | None = None) -> dict:
    print("\n=== Průvodce nastavením scraperu ===")
    print("Enter = přijmout nabízenou hodnotu. Vše lze později změnit přes --setup.\n")
    cfg = dict(DEFAULTS)
    if preset:
        if preset not in PRESETS:
            raise SystemExit(f"Neznámý preset {preset!r}. Dostupné: {', '.join(PRESETS)}")
        cfg.update(PRESETS[preset])
        print(f"Používám hotový profil: {preset}\n")

    # 1) adresa a identita zdroje
    print("--- 1/3 Výchozí stránka ---")
    listing = listing or cfg.get("listing_url") or ""
    listing = ask("Adresa stránky se seznamem témat", listing, yes)
    attempts = 0
    while not listing.startswith(("http://", "https://")):
        attempts += 1
        if yes or attempts > 5:
            raise SystemExit(
                "Chybí platná adresa. Spusťte průvodce s adresou, např.:\n"
                "  python scraper.py --setup --listing https://example.com/forum"
            )
        listing = ask("Adresa musí začínat http:// nebo https://. Zadejte znovu", "", yes)
    cfg["listing_url"] = listing
    parts = urlsplit(listing)
    cfg["base_url"] = f"{parts.scheme}://{parts.netloc}"
    cfg["allowed_hosts"] = [parts.netloc.lower()]

    auto_source, auto_domain = derive_source(listing)
    cfg["source"] = ask("Krátký identifikátor zdroje (adresář a prefix ID)", cfg.get("source") or auto_source, yes)
    cfg["source"] = re.sub(r"[^a-z0-9]+", "", cfg["source"].lower()) or auto_source
    cfg["domain"] = ask("Doména do pole source", cfg.get("domain") or auto_domain, yes)
    cfg["root"] = ask("Kořenová složka pro data", cfg.get("root") or "data", yes)
    print()

    web = None
    soup = None
    if not preset:
        try:
            web = Web(cfg)
            soup = web.soup(listing)
        except Exception as exc:
            print(f"! Stránku se nepodařilo načíst: {exc}")
            print("  Selektory vyplníte ručně (nebo zkuste --test později).\n")

    # 2) seznam témat
    print("--- 2/3 Seznam témat ---")
    if soup is not None:
        clusters = detect_link_clusters(soup, listing, set(cfg["allowed_hosts"]))
        if clusters:
            print("Na stránce jsem našel tyto skupiny odkazů:")
            chosen = ask_choice("Vyberte číslo skupiny odpovídající tématům", clusters, yes=yes)
            if chosen:
                cfg["list_link_selector"] = chosen["selector"]
                try:
                    link = soup.select_one(chosen["selector"])
                    container = guess_container(soup, link) if link else ""
                except Exception:
                    container = ""
                if container:
                    cfg["list_item_selector"] = container
                print(f"  Odkazy: {cfg['list_link_selector']}")
                if cfg["list_item_selector"]:
                    print(f"  Řádek tématu: {cfg['list_item_selector']}")
        else:
            print("! Žádné opakující se odkazy jsem nenašel, vyplňte selektory ručně.")
    cfg["list_link_selector"] = ask("CSS selektor odkazu na téma", cfg.get("list_link_selector") or "a", yes)
    cfg["list_item_selector"] = ask("CSS selektor řádku/obalu tématu (prázdné = hledat odkazy v celé stránce)",
                                    cfg.get("list_item_selector") or "", yes)

    # 3) vlákno
    print("\n--- 3/3 Stránka vlákna ---")
    topic_url = None
    if soup is not None:
        try:
            for a in soup.select(cfg["list_link_selector"]):
                href = a.get("href")
                if href:
                    topic_url = canonical_url(cfg, urljoin(listing, href))
                    if host_of(topic_url) in web.hosts:
                        break
                    topic_url = None
        except Exception:
            topic_url = None
    if topic_url and web is not None:
        print(f"Zkušební vlákno: {topic_url}")
        try:
            topic_soup = web.soup(topic_url)
        except Exception as exc:
            print(f"! Vlákno se nepodařilo načíst: {exc}")
            topic_soup = None
        if topic_soup is not None and not preset:
            blocks = detect_blocks(topic_soup)
            if blocks:
                print("Na stránce vlákna se opakují tyto bloky:")
                chosen = ask_choice("Který blok odpovídá jednomu příspěvku", blocks, yes=yes)
                if chosen:
                    cfg["post_selector"] = chosen["selector"]
            else:
                print("! Opakující se bloky jsem nenašel (web může načítat obsah JavaScriptem).")
            if cfg.get("post_selector"):
                try:
                    sample_blocks = topic_soup.select(cfg["post_selector"])[:5]
                except Exception as exc:
                    print(f"! Neplatný selektor: {exc}")
                    sample_blocks = []
                if sample_blocks:
                    for field, prompt in (
                        ("author", "Autor příspěvku"),
                        ("time", "Čas publikace"),
                        ("text", "Text příspěvku"),
                        ("likes", "Počet lajků"),
                    ):
                        suggestion = suggest_field(sample_blocks, field)
                        if suggestion["selector"]:
                            print(f"\n{prompt}: návrh {suggestion['selector']}"
                                  f" ({suggestion['hits']}/5){': ' + suggestion['sample'] if suggestion['sample'] else ''}")
                        selector = ask(f"  {prompt} – selektor", suggestion["selector"], yes)
                        if field == "author":
                            cfg["author_selector"] = selector
                        elif field == "time":
                            cfg["time_selector"] = selector
                            cfg["time_attr"] = suggestion.get("attr") or ""
                            if selector and not cfg["time_attr"]:
                                cfg["time_attr"] = ask("  Z jakého atributu číst čas (prázdné = text)", "", yes)
                        elif field == "text":
                            cfg["text_selector"] = selector
                        elif field == "likes":
                            cfg["likes_selector"] = selector
                            cfg["likes_attr"] = suggestion.get("attr") or ""
                    cfg["topic_title_selector"] = ask("Nadpis tématu (selektor)", cfg.get("topic_title_selector") or "h1", yes)
                    cfg["next_selector"] = ask("Odkaz na další stránku vlákna", cfg.get("next_selector") or "", yes)
    else:
        print("Vlákno nešlo otevřít, selektory vyplňte ručně.")

    cfg["post_selector"] = ask("CSS selektor jednoho příspěvku", cfg.get("post_selector") or "", yes)
    if not cfg.get("author_selector"):
        cfg["author_selector"] = ask("Autor – selektor uvnitř příspěvku", "", yes)
    if not cfg.get("time_selector"):
        cfg["time_selector"] = ask("Čas – selektor uvnitř příspěvku", "", yes)
    if not cfg.get("text_selector"):
        cfg["text_selector"] = ask("Text – selektor uvnitř příspěvku", "", yes)

    print("\n--- Chování ---")
    cfg["delay"] = float(ask("Prodleva mezi požadavky v sekundách", str(cfg.get("delay", 2.0)), yes) or 2.0)
    cfg["timezone"] = ask("Časová zóna (např. Europe/Prague, UTC)", cfg.get("timezone") or "Europe/Prague", yes)
    cfg["limit"] = ask_int("Max. témat na jeden běh (0 = bez limitu)", int(cfg.get("limit", 20)), yes)
    cfg["max_pages"] = ask_int("Max. stránek vlákna (0 = bez limitu)", int(cfg.get("max_pages", 30)), yes)
    cfg["active_hours"] = ask_int("Okno aktivity tématu v hodinách", int(cfg.get("active_hours", 24)), yes)
    cfg["user_agent"] = ask("User-Agent (identifikujte se pravdivě)", cfg.get("user_agent") or "SchoolScraper/1.0", yes)
    if web is not None:
        web.session.close()

    save_config(config_path, cfg)
    print(f"\nUloženo do {config_path}")
    return cfg


# ------------------------------------------------------------------ config

def load_config(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SystemExit(f"Konfiguraci {path} nelze přečíst: {exc}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Konfigurace {path} není platný JSON: {exc}")
    if not isinstance(raw, dict):
        raise SystemExit(f"Konfigurace {path} musí být JSON objekt.")
    cfg = dict(DEFAULTS)
    cfg.update(raw)
    for key in ("listing_url", "base_url", "source", "post_selector"):
        if not cfg.get(key):
            raise SystemExit(f"V konfiguraci chybí '{key}'. Spusťte --setup.")
    cfg["allowed_hosts"] = [h.lower() for h in (cfg.get("allowed_hosts") or [host_of(cfg["base_url"])])]
    return cfg


def save_config(path: Path, cfg: dict) -> None:
    data = {k: cfg.get(k) for k in DEFAULTS if k in cfg}
    data["allowed_hosts"] = cfg.get("allowed_hosts") or []
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------- main

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Univerzální scraper diskusních vláken do JSONL (DEX-C-826).",
        epilog="Bez přepínačů spustí průvodce nastavením, pokud chybí scraper.json.",
    )
    parser.add_argument("--config", type=Path, default=Path(CONFIG_NAME), help="soubor konfigurace")
    parser.add_argument(
        "--setup", "--ask", dest="setup", action="store_true",
        help="spustit průvodce nastavením (zeptá se na adresu a parametry)",
    )
    parser.add_argument("--preset", choices=sorted(PRESETS), help="hotový profil pro průvodce")
    parser.add_argument("--listing", help="adresa seznamu témat pro průvodce (jinak se na ni zeptá)")
    parser.add_argument("--yes", action="store_true", help="přijmout návrhy bez ptání")
    parser.add_argument("--run", action="store_true", help="jeden ostrý běh (výchozí akce)")
    parser.add_argument("--watch", action="store_true", help="opakovat každou hodinu")
    parser.add_argument("--test", action="store_true", help="jen vypsat vzorek, nic neukládat")
    parser.add_argument("--check", action="store_true", help="zkontrolovat existující JSONL")
    parser.add_argument("--root", help="kořen dat (přepíše konfiguraci)")
    parser.add_argument("--limit", type=int, help="max. témat na běh")
    parser.add_argument("--max-pages", type=int, help="max. stránek vlákna")
    parser.add_argument("--active-hours", type=int, help="okno aktivity v hodinách")
    parser.add_argument("--log-file", type=Path, help="zapisovat log i do souboru (rotace)")
    parser.add_argument("--debug", action="store_true", help="podrobný log")
    args = parser.parse_args(argv)

    handlers = [logging.StreamHandler()]
    if args.log_file:
        args.log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(args.log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"))
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )

    fresh = False
    if args.setup or not args.config.exists():
        if not args.setup and not sys.stdin.isatty():
            raise SystemExit(
                f"Chybí {args.config} a běh není interaktivní. Spusťte:\n"
                f"  python {Path(sys.argv[0]).name} --setup --preset discourse"
            )
        wizard(args.config, args.preset, args.yes, args.listing)
        fresh = True
        print()
    cfg = load_config(args.config)

    if args.root:
        cfg["root"] = args.root
    if args.limit is not None:
        cfg["limit"] = args.limit
    if args.max_pages is not None:
        cfg["max_pages"] = args.max_pages
    if args.active_hours is not None:
        cfg["active_hours"] = args.active_hours
    if min(cfg["limit"], cfg["max_pages"], cfg["active_hours"]) < 0:
        raise SystemExit("Číselné parametry nesmí být záporné.")

    root = Path(cfg.get("root") or "data")
    root.mkdir(parents=True, exist_ok=True)
    if args.check:
        return validate(cfg, root)
    if args.test or fresh:
        return dry_run(cfg, args)
    try:
        with single_instance(root / ".scraper.lock"):
            return loop(cfg, args)
    except LockBusy:
        logging.error("Nad %s už běží jiná instance, končím.", root)
        return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
