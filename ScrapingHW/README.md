# Univerzální scraper diskusních vláken → JSONL

Projekt **DEX-C-826**. Jeden skript (`scraper.py`), který stáhne seznam témat z diskusního
fóra, otevře každé vlákno, uloží téma a jeho komentáře do JSONL — a **není svázaný
s jedním webem**. Všechno, co je specifické pro konkrétní fórum (adresy, CSS selektory,
formáty data), je v souboru `scraper.json`. Ten se dá buď napsat ručně, nebo nechat
vygenerovat průvodcem, který se při spuštění zeptá a selektory sám zkusí najít.

Původní skript z prezentace uměl jen `discuss.python.org`. Tenhle umí i jiná fóra,
jiné jazyky a jiné datumové formáty — a hlavně se dá **poslat spolužákovi, aby si ho
nakonfiguroval na svůj web**, aniž by musel sahat do kódu.

---

## 1. Instalace

```bash
python -m pip install -r requirements.txt
```

Obsah `requirements.txt`:

```
requests>=2.28
beautifulsoup4>=4.11
tzdata; sys_platform == "win32"
```

- Potřebuje **Python 3.9 a novější** (používá `zoneinfo`).
- Na Windows je `tzdata` potřeba, protože systém nemá databázi časových zón.
  Bez něj skript vypíše srozumitelnou chybu a ostatní funkce fungují dál.
- Ověřeno na Pythonu 3.12 a 3.14, Linux; na Windows stačí stejné balíčky.

---

## 2. Rychlý start (tři příkazy)

```bash
python scraper.py            # 1) průvodce: zeptá se na adresu, najde selektory, udělá zkušební běh
python scraper.py --run      # 2) ostrý běh
python scraper.py --check    # 3) kontrola, že výstup odpovídá datovému modelu
```

Když `scraper.json` ještě neexistuje, první příkaz se sám zeptá. Když existuje,
`python scraper.py` rovnou spustí jeden běh — takže pro spolužáka je to opravdu
„stáhni, spusť, odpověz na pět otázek“.

Opakované stahování (nové příspěvky každou hodinu):

```bash
python scraper.py --run --watch
```

---

## 3. Průvodce nastavením

`python scraper.py --setup` (zkratka `--ask`, nebo první spuštění bez konfigurace)
projde tyto kroky:

1. **Adresa seznamu témat** — např. `https://discuss.python.org/c/help/7`.
2. **Zkušební vlákno** — průvodce otevře první odkaz ze seznamu a vypíše bloky, které
   se na stránce opakují. Uživatel vybere, který blok je jeden příspěvek.
3. **Selektory polí** — pro autora, čas, text a lajky navrhne selektor sám (hledá
   atributy typu `rel="author"`, `itemprop`, `class` obsahující `author`/`time`/`post`…)
   a ukáže, na kolika z pěti vzorků zabral. Uživatel může návrh potvrdit nebo přepsat.
4. **Chování** — prodleva, časová zóna, limity, User-Agent.

Užitečné přepínače průvodce:

| Přepínač | Význam |
|---|---|
| `--preset discourse` | předvyplní hotový profil pro Discourse (discuss.python.org) |
| `--listing URL` | adresa seznamu témat předem, průvodce se na ni neptá |
| `--yes` | přijme všechny návrhy bez ptání (vhodné pro testování a CI) |

Hotový profil pro discuss.python.org je i v `scraper.example.json` — stačí ho
zkopírovat na `scraper.json` a spustit `--run`.

**Co průvodce neumí:** weby, které obsah načítají JavaScriptem. Tam je potřeba
prohlížeč (viz část 9).

---

## 4. Co skript dělá při běhu

1. Načte `robots.txt` a zkontroluje, jestli se smí stránky stahovat.
2. Projde seznam témat, přečte odkaz, název a případně čas poslední aktivity.
3. Témata seřadí (nová první) a omezí podle `active_hours` a `limit`.
4. U každého vlákna projde stránky (`rel="next"`, `?page=`, nebo šablona v `page_url_template`).
5. První příspěvek = téma, ostatní = komentáře. Zapisuje se jen to, co v souboru ještě není.
6. Mezi požadavky čeká `delay` sekund; při 429/5xx zkouší znovu s rostoucí prodlevou
   a respektuje `Retry-After`.
7. Stav (co už je stažené, kdy naposledy) drží v `data/state.json`, aby se po přerušení
   nezačínalo od nuly a nevznikaly duplicity.

Bezpečnostní pojistky: `allowed_hosts` (nikam jinam se neposílá požadavek), zámek
`.scraper.lock` (druhá instance skončí kódem 2), limit stránek na vlákno a `timeout`.

---

## 5. Výstup

```
data/<zdroj>/<rok>/<měsíc>/<zdroj>-<YYMMDD>-<hash8>.jsonl
```

Příklad: `data/python/2022/05/python-220530-6aa0dd95.jsonl`

- První řádek souboru je **téma** (`"type": "topic"`), další řádky **komentáře**
  (`"type": "comment"`). Jeden JSON objekt na řádek, UTF-8, `ensure_ascii=False`.
- Nové komentáře se **připojují na konec** souboru — model je append-only.
- Datum v cestě je datum **publikace tématu**. Kdyby to bylo datum stažení, každý den
  by vznikl jiný soubor a připojování by ztratilo smysl.

Pole tématu: `type, topic_id, source, url, title, author, published_at, scraped_at`.

Pole komentáře: `type, comment_id, topic_id, parent_id, author, published_at,
scraped_at, text, likes, dislikes`. Když web vztah nebo lajky neposkytuje, je tam
`null` — nic se nevymýšlí. Když se čas nepodaří přečíst, uloží se `published_at: null`
a k tomu `published_at_raw` s původním textem, aby se dalo datum dohledat.

Identifikátory:

- `topic_id` = `<zdroj>_<8 znaků MD5 z URL tématu>` — přežije změnu slugu i přejmenování.
- `comment_id` = `<zdroj>_c_<nativní ID>`, pokud ho web má (`post_11`);
  jinak `<zdroj>_c_<8 znaků MD5 z autora + času + textu>`, přesně jak žádá zadání.

---

## 6. Konfigurace (`scraper.json`)

Soubor se ukládá průvodcem, ale dá se psát i ručně. Nevyplněná pole se berou
z výchozích hodnot v kódu, takže stačí uvést to, co je pro daný web jinak.

### Web a výstup

| Pole | Význam | Příklad |
|---|---|---|
| `base_url` | kořen webu | `https://discuss.python.org` |
| `allowed_hosts` | domény, kam se smí posílat požadavky | `["discuss.python.org"]` |
| `source` | zkratka zdroje do ID a do cesty | `python` |
| `domain` | hodnota pole `source` v záznamu | `discuss.python.org` |
| `root` | kořen dat | `data` |
| `user_agent` | UA, kterým se skript představí | `PythonForumSchoolScraper/1.0` |

### Seznam témat

| Pole | Význam |
|---|---|
| `listing_url` | adresa stránky se seznamem témat (může být i stránkovaná) |
| `list_item_selector` | jeden řádek seznamu (`tr.topic-list-item`) |
| `list_link_selector` | odkaz na téma uvnitř řádku (`a.raw-topic-link`) |
| `list_activity_selector` | nepovinné: kde je čas poslední aktivity (u Discoursu `td:last-of-type`) |
| `list_activity_attr` | atribut s časem (`datetime`, `title`, `data-time`, `text`) |

Když je čas aktivity známý a starší než `--active-hours`, téma se přeskočí. U Discoursu
je ve sloupci Activity jen datum bez času (`November 15, 2026`), takže se bere jako
půlnoc v `timezone`; téma aktivní včera večer může proto vypadnout. Pomůže `--active-hours 48`.

### Vlákno

| Pole | Význam |
|---|---|
| `post_selector` | jeden příspěvek (`div.topic-body.crawler-post`) |
| `post_id_attr` | atribut s nativním ID (`id`) |
| `post_id_regex` | jak z atributu vytáhnout číslo (`post_(\d+)`) |
| `native_id_template` | jak složit výsledné ID (`{topic}_{id}`) |
| `topic_from` | `first_post` (výchozí) nebo `header` — viz níže |
| `topic_title_selector` | nadpis tématu (`#topic-title h1`) |
| `topic_selector` | blok s hlavičkou tématu, pokud je mimo seznam příspěvků |
| `topic_author_selector`, `topic_time_selector`, `topic_time_attr` | autor a čas z hlavičky |
| `author_selector` | autor příspěvku (`[itemprop="name"]`) |
| `time_selector`, `time_attr` | čas příspěvku (`time.post-time`, `datetime`) |
| `text_selector` | tělo příspěvku (`.post[itemprop="text"]`) |
| `text_separator` | čím oddělit odstavce (výchozí `\n`) |
| `likes_selector`, `likes_attr` | lajky (`meta[itemprop="upvoteCount"]`, `content`) |
| `parent_selector`, `parent_regex` | nepovinné: vztah „odpověď na“ (citace) |
| `next_selector` | odkaz na další stránku (`link[rel="next"]`) |
| `page_url_template` | když web stránkování neznačí odkazem: `{url}?page={page}` |

**`topic_from`** rozhoduje, odkud se vezme téma:

- `first_post` — první příspěvek ve vlákně je téma (Discourse, phpBB, většina fór).
- `header` — téma je v samostatné hlavičce (`topic_selector`) a první příspěvek
  je normální komentář (weby se seznamem „vlákno + N odpovědí“).

### Chování

| Pole | Význam | Výchozí |
|---|---|---|
| `time_formats` | seznam `strptime` formátů, zkouší se popořadě | české i anglické |
| `timezone` | zóna pro časy bez offsetu | `Europe/Prague` |
| `delay` | prodleva mezi požadavky (s) | `2.0` |
| `timeout` | timeout jednoho požadavku (s) | `25` |
| `retries` | počet pokusů při 429/5xx | `3` |
| `limit` | max. témat na běh (`0` = bez limitu) | `20` |
| `max_pages` | max. stránek jednoho vlákna (`0` = bez limitu) | `30` |
| `active_hours` | stahovat jen témata aktivní za posledních N hodin (`0` = všechna) | `24` |
| `keep_query` | brát query z odkazů jako součást identity tématu | `false` |
| `store_unparsed_time` | u nepřečteného času uložit `published_at_raw` | `true` |

Časy se čtou třemi způsoby: jako ISO 8601 (`2022-05-30T15:37:55+00:00`), podle
`time_formats`, a nakonec jako český textový měsíc (`21. října 2026 14:30`).
Když selektor počítá s atributem (`time[datetime]`), ale stránka atribut nemá,
zkusí se stejný selektor bez podmínek na atributy a přečte se text — jinak by
jedno takové vlákno shodilo celý běh.

---

## 7. Adaptace na vlastní web (pro spolužáky)

1. **Najdi stránku se seznamem témat** (ne jednotlivé vlákno) a vlož ji do průvodce.
2. **Otevři jedno vlákno** v prohlížeči, klikni pravým → *Prozkoumat prvek*:
   - jeden příspěvek = jeden opakující se blok (často `<article>`, `<div class="post">`),
   - autor, čas a text jsou potomci tohoto bloku.
3. **Spusť `python scraper.py --setup`** a nech si poradit; návrhy zkontroluj.
4. **Ověř na vzorku:** `python scraper.py --test --limit 1` — jen vypíše, co by se
   uložilo, nic nezapisuje.
5. **Zkontroluj data:** `python scraper.py --check` — ověří JSON, povinná pole,
   ID, duplicity a shodu cesty s datem.
6. Když něco nesedí, uprav jeden selektor v `scraper.json` a znovu `--test`.
   Do kódu sahat nemusíš.

Časté situace:

| Situace | Řešení |
|---|---|
| příspěvky nemají `id` | nech `post_id_attr` prázdné → ID se spočítá z hashe |
| datum je jen text (`13. listopadu 2026 7:45`) | `time_attr` nech prázdné, přidej formát do `time_formats` |
| vlákno má víc stránek bez odkazu „další“ | `page_url_template`: `{url}?page={page}` |
| hlavička tématu je mimo příspěvky | `topic_from: "header"` + `topic_selector` |
| web má víc šablon stránek | jeden config na šablonu (`--config scraper-b.json`) |

---

## 8. Příkazy

| Příkaz | Co dělá |
|---|---|
| `python scraper.py` | běh (bez configu nejdřív průvodce) |
| `--setup` (nebo `--ask`) | průvodce nastavením, nabídne současné hodnoty |
| `--run` | jeden ostrý běh |
| `--run --watch` | běh každou hodinu |
| `--test` | vzorek na obrazovku, nic se neukládá |
| `--check` | validace existujících JSONL, kód 0/1 |
| `--config FILE` | jiná konfigurace (např. druhý web) |
| `--root DIR` | jiný kořen dat |
| `--limit N`, `--max-pages N`, `--active-hours N` | přepíše hodnoty z configu pro jeden běh |
| `--log-file FILE` | log i do souboru (rotace po 1 MB, 3 zálohy) |
| `--debug` | podrobný log |

Návratové kódy: `0` úspěch, `1` chyba validace, `2` už běží jiná instance,
`130` přerušeno Ctrl+C.

---

## 9. Když web načítá obsah JavaScriptem

`requests` vidí jen to, co přijde v HTML. Pokud je seznam nebo příspěvky až
v DOM po spuštění JS, má smysl sáhnout po prohlížeči — k tomu slouží
`scraper_live_playwright.py` z původního odevzdání. Tenhle skript se pak používá
jako „rychlá cesta“ pro weby se serverovým HTML.

Rozdíl je i v tom, co web vrátí: discuss.python.org posílá crawlerům jinou
stránku (třída `crawler` v `<body>`, datum jen jako text). Lajky tam nejsou
vidět v UI, ale v HTML jsou jako `meta[itemprop="upvoteCount"]` uvnitř bloku
příspěvku, takže je scraper čte. Preset v `scraper.example.json` je postavený
na této podobě.

---

## 10. Co je ověřené a co ne

Ověřeno běhy (ne od oka):

| Test | Výsledek |
|---|---|
| Živý discuss.python.org, preset `discourse` | 30 témat na seznamu; vlákno 42 → 4 komentáře, lajky 0 a 4, časy v UTC |
| Okno aktivity `--active-hours 24` na živém webu | ze 30 témat prošla 2 s aktivitou 15. 11.; připnuté téma s aktivitou 31. 5. 2022 přeskočeno |
| Stránkování živého vlákna (106691, `--max-pages 2`) | 39 komentářů z ID `post_2`…`post_44`, `complete: false` (limit stránek), čas posledního příspěvku 2026-03-27 |
| Průvodce bez presetu na živém discuss.python.org | sám našel `a[href*="/t"]`, řádek `span.link-top-line` a příspěvek `div.topic-body.crawler-post`; 4 komentáře, lajky 6/0/4 |
| Lokální testovací web, jiný markup | průvodce sám našel `article.post`, `h2.thread-title`, `.username`, `time[datetime]`; 3 komentáře, 2 stránky |
| Druhá šablona na tomtéž webu, čas jen jako text | `13. listopadu 2026 7:45` → `2026-11-13T07:45:00+01:00` |
| Příspěvky bez `id` (`div.msg`) | náhradní ID `localhost_c_<hash>` stabilní mezi běhy |
| Hlavička tématu mimo příspěvky | `topic_from: "header"` vrátil nadpis, autora i datum z hlavičky, první příspěvek jako komentář |
| `--check` na výstupu | 0 chyb, 0 varování |

Neověřeno / limity:

- Weby za loginem a CAPTCHA se **neobcházejí** — skript končí chybou, jak má.
- Weby s JS obsahem: potřeba Playwright varianta.
- Jeden config = jedna šablona stránky. Web, který míchá dvě šablony vláken,
  bude na té druhé hlásit „selektor nic nenašel“ (a pokračuje dál).
- `dislikes` a `parent_id` jsou `null`, protože je zdroj v HTML nenabízí.

---

## 11. Slušné chování vůči webu

- `robots.txt` se respektuje včetně wildcardů (`Disallow: /t/*/*.rss`).
  Když robots.txt chybí (404), bere se to jako „procházení povoleno“.
- Prodleva `delay` mezi požadavky (výchozí 2 s), žádné paralelní stahování.
- Při 429/503 se čeká podle `Retry-After`, jinak exponenciálně (1, 2, 4 s).
- User-Agent se identifikuje pravdivě; nikde není vydávání se za prohlížeč.
- `allowed_hosts` brání tomu, aby se požadavky omylem poslaly na cizí doménu
  (např. přes odkaz v příspěvku).
- Malý vzorek: `--limit`, `--max-pages` a `active_hours` drží zátěž na minimu.

---

## 12. Mapování na zadání

| Požadavek zadání | Kde je v kódu |
|---|---|
| seznam témat → odkazy | `discover()` |
| otevření vlákna, stránkování | `read_topic()` |
| první příspěvek = téma, ostatní komentáře | `read_topic()`, `topic_from` |
| `topic_id` z MD5 URL | `make_topic()` |
| `comment_id` z nativního ID nebo hashe | `comment_id_for()` |
| JSONL, jedno vlákno = jeden soubor | `append_topic()` |
| cesta `<zdroj>/<rok>/<měsíc>/<soubor>` | `append_topic()` |
| jen nové komentáře (append-only) | `append_topic()`, `state.json` |
| robots.txt, prodleva, UA | `Web` |
| ošetření chyb a opakování | `Web.get()`, `loop()` |
| dokumentace a spuštění | tento soubor + `--help` |

---

## 13. Co říct u obhajoby

- „Skript není napevno na jeden web: selektory jsou v konfiguraci, takže ho
  spolužák použije na svoje fórum bez úpravy kódu.“
- „Průvodce sám navrhne selektory z živé stránky a ukáže, na kolika vzorcích
  zabraly — nastavení je otázka minuty, ne hodiny hledání v DevTools.“
- „`--check` je důkaz, že výstup odpovídá datovému modelu; dá se pustit při obhajobě.“
- „Identifikátory jsou stabilní: `topic_id` z URL, `comment_id` z nativního ID,
  a když web ID nemá, z hashe autora, času a textu.“
- „Omezení jsou pojmenovaná, ne zamlčená: `parent_id` a `dislikes` jsou `null`,
  protože je HTML neobsahuje; weby s JS potřebují Playwright.“
