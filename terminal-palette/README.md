# Terminálová paleta 16 barev

Tato složka obsahuje skripty pro vykreslení palety 16 standardních barev přednastavených v terminálu.

## Dostupné skripty

### 1. **palette.sh** (Bash)
```bash
chmod +x palette.sh
./palette.sh
```

Vykreslí:
- Řádkový seznam barev 0-7 (standardní)
- Řádkový seznam barev 8-15 (jasné)
- Mřížka 4x4 barev
- Příklady použití

### 2. **palette.py** (Python 3)
```bash
python3 palette.py
# nebo
chmod +x palette.py
./palette.py
```

Stejný výstup jako Bash verze, ale v Pythonu.

## Co dělají skripty

Oba skripty vykreslují:

1. **16 standardních barev** s jejich čísly a názvy:
   - 0-7: Základní barvy (Black, Red, Green, Yellow, Blue, Magenta, Cyan, White)
   - 8-15: Jasné verze (Bright Black až Bright White)

2. **Vizuální mřížka** barev v tabulce 4x4

3. **Příklady kódu** jak používat barvy ve vašich programech

## Příklad výstupu

```
╔═══════════════════════════════════════════════════════════════════════════╗
║          16-Color Terminal Palette (Standardní barvy terminálu)          ║
╚═══════════════════════════════════════════════════════════════════════════╝

Standardní barvy (0-7):

   0    Black
   1    Red
   2    Green
   3    Yellow
   4    Blue
   5    Magenta
   6    Cyan
   7    White

Jasné barvy (8-15):

   8    Bright Black
   9    Bright Red
  10    Bright Green
  11    Bright Yellow
  12    Bright Blue
  13    Bright Magenta
  14    Bright Cyan
  15    Bright White

[... mřížka a další obsah ...]
```

## Jak používat barvy v terminálu

### Bash/Shell
```bash
# Barva textu (přední barva)
echo -e '\033[38;5;1mČervený text\033[0m'

# Barva pozadí
echo -e '\033[48;5;2mZelené pozadí\033[0m'

# Kombinace
echo -e '\033[48;5;1m\033[38;5;15mBílý text na červeném pozadí\033[0m'
```

### Python
```python
# Barva textu
print('\033[38;5;1mČervený text\033[0m')

# Barva pozadí
print('\033[48;5;2mZelené pozadí\033[0m')

# Kombinace
print('\033[48;5;1m\033[38;5;15mBílý text na červeném pozadí\033[0m')
```

## Čísla barev

| Číslo | Barva |
|------|-------|
| 0 | Black (Černá) |
| 1 | Red (Červená) |
| 2 | Green (Zelená) |
| 3 | Yellow (Žlutá) |
| 4 | Blue (Modrá) |
| 5 | Magenta (Purpurová) |
| 6 | Cyan (Azurová) |
| 7 | White (Bílá) |
| 8 | Bright Black (Jasná černá) |
| 9 | Bright Red (Jasná červená) |
| 10 | Bright Green (Jasná zelená) |
| 11 | Bright Yellow (Jasná žlutá) |
| 12 | Bright Blue (Jasná modrá) |
| 13 | Bright Magenta (Jasná purpurová) |
| 14 | Bright Cyan (Jasná azurová) |
| 15 | Bright White (Jasná bílá) |

## Poznámky

- Barvy se mohou lišit v závislosti na tématu vašeho terminálu
- Oba skripty jsou kompatibilní s Linux, macOS a Windows (WSL)
- Pro Windows PowerShell možná budete potřebovat aktivovat ANSI escape sekvence
