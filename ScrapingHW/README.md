# Extrakce diskusí z discuss.python.org

Projekt **DEX-C-826**. Skript `python_forum_scraper_v2.py` stáhne kategorii
[Python Help](https://discuss.python.org/c/help/7), z každého vlákna uloží téma
a komentáře do JSONL a nové komentáře jen připisuje.

Web, selektory i zdroj jsou v kódu. Konfigurace v `scraper.json` se nepoužívá.

## Spuštění

```bash
python -m pip install requests beautifulsoup4

python python_forum_scraper_v2.py data              # jeden běh
python python_forum_scraper_v2.py data --watch      # znovu každou hodinu
python python_forum_scraper_v2.py data --check      # kontrola uložených JSONL
```

`data` je kořenová složka. Do ní se ukládají JSONL i `state.json`.

`--watch` po každém cyklu čeká, aby další běh začal hodinu po startu předchozího
(`loop()` v `python_forum_scraper_v2.py`). Když cyklus trvá déle než hodinu,
další začne hned. Proces nechte běžet; ukončení je Ctrl+C.

## Co jeden běh udělá

1. Zamkne `data/.scraper.lock`. Druhá instance skončí s kódem 2.
2. Načte `robots.txt` a drží prodlevu aspoň 2 s mezi požadavky.
3. `discover()` přečte seznam témat na titulní straně kategorie.
4. Přeskočí už zpracovaná témata, která nebyla aktivní v posledních 24 hodinách
   (`--active-hours`, výchozí 24). Nové téma stáhne vždy.
5. `read_topic()` projde stránky vlákna (`link[rel="next"]`).
6. `append_topic()` zapíše téma a připojí jen komentáře, které v souboru ještě nejsou.
7. `save_state()` uloží `data/state.json`.

Na jeden běh je nejvýš 20 témat (`--limit`) a 30 stránek vlákna (`--max-pages`).
Nezpracovaná témata jdou první, takže limit nová vlákna nevyhladoví.

## Kam se to ukládá

```
data/python/<rok>/<měsíc>/python-<YYMMDD>-<hash8>.jsonl
data/state.json
data/.scraper.lock
```

Příklad: `data/python/2026/11/python-261115-05ff9665.jsonl`

Datum v cestě i v názvu je datum **publikace** úvodního příspěvku. Kdyby to bylo
datum stažení, vznikl by každý den jiný soubor a připisování by se rozbilo.

První řádek souboru je téma, další řádky komentáře. Jeden JSON objekt na řádek, UTF-8.

Téma: `type`, `topic_id`, `source`, `url`, `title`, `author`, `published_at`, `scraped_at`.

Komentář: `type`, `comment_id`, `topic_id`, `parent_id`, `author`, `published_at`,
`scraped_at`, `text`, `likes`, `dislikes`.

- `topic_id` je `python_` a posledních 8 znaků MD5 z kanonické URL vlákna.
- `source` v záznamu je `discuss.python.org`. Složka a prefix ID jsou `python`.
- `comment_id` je `python_c_<číslo vlákna>_<číslo příspěvku>`.
- `likes` je `meta[itemprop="upvoteCount"]`. `dislikes` je vždy `null`.
- `parent_id` je vždy `null`. Crawler HTML Discourse vztah „odpověď na“ nemá.
- Text úvodního příspěvku se neukládá. Zadání u tématu pole `text` nemá, bere se název z `#topic-title h1`.
- Úpravy a smazání už uložených příspěvků se nepřenášejí. Soubor je jen na připisování.

`state.json` drží `last_run`, `processed_topics`, `topic_urls` a `last_activity`.
Díky `topic_urls` zůstane stejný soubor i po změně slugu v URL.

## Příkazy

| Příkaz | Co dělá |
|---|---|
| `python python_forum_scraper_v2.py data` | jeden běh |
| `python python_forum_scraper_v2.py data --watch` | opakovat každou hodinu |
| `python python_forum_scraper_v2.py data --check` | zkontrolovat JSONL, kód 0 nebo 1 |
| `--limit N` | max. témat na běh, výchozí 20, `0` = bez limitu |
| `--max-pages N` | max. stránek jednoho vlákna, výchozí 30, `0` = bez limitu |
| `--active-hours N` | okno aktivity v hodinách, výchozí 24, musí být aspoň 1 |
| `--log-file SOUBOR` | log i do souboru, rotace po 1 MB, 3 zálohy |

Návratové kódy: `0` úspěch, `1` chyba kontroly nebo cyklu, `2` už běží jiná instance, `130` Ctrl+C.

## Kde je to v kódu

| Krok | Funkce |
|---|---|
| HTTP, robots.txt, prodleva, retry | `Web` |
| seznam témat z titulní strany | `discover()` |
| stránky vlákna, téma a komentáře | `read_topic()` |
| cesta souboru a připojení nových řádků | `append_topic()` |
| index zpracovaných témat | `load_state()`, `save_state()` |
| jeden cyklus | `run()` |
| opakování každou hodinu | `loop()` |
| kontrola datového modelu | `validate()` |
| zámek jedné instance | `single_instance()` |

## Co říct u obhajoby

- Skript jede trvale: `python python_forum_scraper_v2.py data --watch` spouští další cyklus hodinu po začátku předchozího.
- Datum v cestě je datum publikace, proto se nové komentáře připojují do stejného souboru.
- `parent_id` a `dislikes` jsou `null`, protože je crawler HTML nenabízí. Lajky se berou z `upvoteCount`.
