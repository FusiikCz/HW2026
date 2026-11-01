# HW2026

Zadání úkolů a kde je řešení.

## 1. OWASP Juice Shop

V aplikaci OWASP Juice Shop si kupte Vánoční speciál z roku 2014 a při nákupu uplatněte kupón na 50% slevu z října 2026. Postup podrobně popište a doložte snímky obrazovek.

Složka: `1-owasp-juiceshop`  
Sem patří popis postupu a snímky. Nákup v aplikaci zatím není hotový.

## 2. Paleta barev terminálu

Vytvořte skript, který vykreslí paletu 16 odstínů barev přednastavených v terminálu.

Tři sloupce v pořadí barev konzole: název, název tou barvou, název na barevném pozadí.

Složka: `2-paleta`

```powershell
powershell -File .\2-paleta\paleta.ps1
```

## 3. Aliasy

Vytvořte alias np (notepad.exe) a ct (control.exe). Oba aliasy si zálohujte do formátu JSON a také do formátu XML. Potom oba aliasy smažte a obnovte je z JSON souboru. Znovu je smažte a obnovte z XML souboru.

Složka: `3-aliasy`

```powershell
powershell -File .\3-aliasy\aliasy.ps1
```

Skript aliasy vytvoří, uloží `aliasy.json` a `aliasy.xml`, smaže je, obnoví z JSON, znovu smaže a obnoví z XML. Po skončení v té relaci platí `np` a `ct`.

## 4. Palindrom

Vytvořte program v PowerShellu, který ověří, že zadaný text je palindrom. K testu použijte např. "Jelenovi pivo nelej", "Kobyla má malý bok", "Kupředu udeř puk", "Dal kopat Ota poklad", "Toto není palindrom".

Složka: `4-palindrom`

```powershell
powershell -File .\4-palindrom\palindrom.ps1
powershell -File .\4-palindrom\palindrom.ps1 "Jelenovi pivo nelej"
```

Bez argumentu ověří pět vět ze zadání. Věta „Toto není palindrom“ palindrom není. Mezery, interpunkce, velikost písmen a diakritika se při porovnání nepočítají.

## Statistika textu

Na stránce se zadáním tento úkol nemá číslo.

Vytvořte program, kterému v terminálu předám text, a on mi vypíše počet znaků textu s mezerami i bez mezer, počet samohlásek a počet slov.

Složka: `5-statistiky`

```powershell
powershell -File .\5-statistiky\statistiky.ps1 "Jelenovi pivo nelej"
powershell -File .\5-statistiky\statistiky.ps1
```

Když text chybí, skript se na něj zeptá. Samohlásky jsou a, á, e, é, ě, i, í, o, ó, u, ú, ů, y, ý.

Věta o Lewisi Powellovi ze zadání vychází na 219 znaků s mezerami, 77 samohlásek a 31 slov.

## 5. CIM

K řešení následujících úloh použijte CIM rozhraní.

1. Zjistěte vlastnosti třídy umožňující spravovat tiskárny. Změňte umístění faxu.
2. V informačních systémech MO se disk C: nazývá "System" a disk D: nazývá "Data". Zjistěte, jak se nazývá váš disk C: a případně ho přejmenujte na "System".
3. Vypište seznam nepoužitých účtů (účtů, ke kterým se nikdo nikdy nepřihlásil) a seznam uzamčených účtů. Porovnejte řešení pomocí vhodného příkazu PowerShellu pro práci s uživatelskými účty a řešení pomocí CIM rozhraní.

Složka: `5-cim`

```powershell
powershell -File .\5-cim\reseni.ps1
```

Třída tiskáren je `Win32_Printer`. Popisek disku je `Win32_Volume`. Uzamčení účtu je `Win32_UserAccount.Lockout`, přihlášení doplňuje `Win32_UserProfile`. `Get-LocalUser` Lockout nemá.
