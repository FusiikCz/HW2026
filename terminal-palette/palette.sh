#!/usr/bin/env bash
# -*- coding: utf-8 -*-
#
# Terminal 16-Color Palette Viewer (Bash)
# Vykreslí paletu 16 standardních barev terminálu.
#
# Poznámky k opravám:
#   - Nastavuje UTF-8 locale, aby Bash počítal DÉLKU V ZNACÍCH (ne v bajtech).
#     Bez toho se diakritika (í, á) počítá jako 2 bajty a rámeček se rozjede.
#   - Kontrastní barva textu (černá/bílá podle jasu pozadí) -> "Color 7"
#     a "Color 15" už nejsou bílé na bílém.
#   - Dynamická šířka rámečku.
#   - Mezery mezi dlaždicemi v mřížce.

# --- UTF-8 locale (nutné pro správné počítání znaků) -------------------------
# Zkusíme nastavit UTF-8 locale; pokud není k dispozici, zůstaneme na výchozím.
for loc in C.UTF-8 C.utf8 en_US.UTF-8 en_US.utf8; do
    if locale -a 2>/dev/null | grep -qi "^${loc}$"; then
        export LC_ALL="$loc"
        break
    fi
done

RESET=$'\033[0m'
BOX_WIDTH=75

# Názvy barev (indexy 0-15)
COLOR_NAMES=(
    "Black" "Red" "Green" "Yellow"
    "Blue" "Magenta" "Cyan" "White"
    "Bright Black" "Bright Red" "Bright Green" "Bright Yellow"
    "Bright Blue" "Bright Magenta" "Bright Cyan" "Bright White"
)

# Barva textu (fg) pro každé pozadí (bg) 0-15 – zajišťuje čitelnost.
# (0 = černá, 15 = bílá)
FG_FOR_BG=(
    15  # 0  Black          -> bílý text
    15  # 1  Red            -> bílý text
    15  # 2  Green          -> bílý text
    0   # 3  Yellow         -> černý text
    15  # 4  Blue           -> bílý text
    15  # 5  Magenta        -> bílý text
    0   # 6  Cyan           -> černý text
    0   # 7  White          -> černý text  (oprava: bílá na bílé = neviditelná)
    15  # 8  Bright Black   -> bílý text
    15  # 9  Bright Red     -> bílý text
    15  # 10 Bright Green   -> bílý text
    0   # 11 Bright Yellow  -> černý text
    15  # 12 Bright Blue    -> bílý text
    15  # 13 Bright Magenta -> bílý text
    0   # 14 Bright Cyan    -> černý text
    0   # 15 Bright White   -> černý text  (oprava)
)

# --- Pomocné funkce ----------------------------------------------------------

# Zopakuje znak N-krát: repeat_char "═" 75
repeat_char() {
    local ch="$1" n="$2" s=""
    local i
    for (( i = 0; i < n; i++ )); do s+="$ch"; done
    printf '%s' "$s"
}

print_separator() {
    local title="${1:-}"
    local inner="${2:-$BOX_WIDTH}"
    # Rámeček nikdy nesmí být užší než titulek (+2 mezery).
    (( inner < ${#title} + 2 )) && inner=$(( ${#title} + 2 ))

    local bar; bar="$(repeat_char "═" "$inner")"
    local left right lpad rpad
    left=$(( (inner - ${#title}) / 2 ))
    right=$(( inner - ${#title} - left ))
    lpad="$(printf '%*s' "$left" '')"
    rpad="$(printf '%*s' "$right" '')"

    printf '╔%s╗\n' "$bar"
    printf '║%s%s%s║\n' "$lpad" "$title" "$rpad"
    printf '╚%s╝\n' "$bar"
    echo
}

# Vykreslí dlaždici: barevné pozadí + číslo a za ním barevný název.
print_color_line() {
    local i="$1"
    local fg="${FG_FOR_BG[$i]}"
    local name="${COLOR_NAMES[$i]}"
    printf '\033[48;5;%dm\033[38;5;%dm  %2d  %s' "$i" "$fg" "$i" "$RESET"
    printf '  \033[38;5;%dm%s%s\n' "$i" "$name" "$RESET"
}

# --- Sekce -------------------------------------------------------------------

section_standard() {
    echo "Standardní barvy (0-7):"
    echo
    local i
    for i in {0..7}; do print_color_line "$i"; done
}

section_bright() {
    echo
    echo "Jasné barvy (8-15):"
    echo
    local i
    for i in {8..15}; do print_color_line "$i"; done
}

section_grid() {
    echo
    print_separator "Náhled barev v mřížce"
    echo "Mřížka 4x4:"
    echo
    local row col color fg line
    for (( row = 0; row < 4; row++ )); do
        line=""
        for (( col = 0; col < 4; col++ )); do
            color=$(( row * 4 + col ))
            fg="${FG_FOR_BG[$color]}"
            line+="$(printf '\033[48;5;%dm\033[38;5;%dm  %2d  %s' \
                        "$color" "$fg" "$color" "$RESET")"
            (( col < 3 )) && line+="  "   # mezera mezi dlaždicemi
        done
        printf '  %s\n' "$line"
    done
}

section_text() {
    echo
    print_separator "Jednotlivé barvy s textem"
    echo
    local i fg
    for i in {0..15}; do
        fg="${FG_FOR_BG[$i]}"
        printf '\033[48;5;%dm\033[38;5;%dm Color %2d %s' "$i" "$fg" "$i" "$RESET"
        (( (i + 1) % 4 == 0 )) && echo
    done
    echo
}

section_usage() {
    echo
    print_separator "Použití barev ve vašich skriptech a programech"
    echo
    echo "Python:"
    echo "  print('\\033[38;5;<NUM>mText\\033[0m')  # Barva textu"
    echo "  print('\\033[48;5;<NUM>mText\\033[0m')  # Barva pozadí"
    echo
    echo "Bash:"
    echo "  echo -e '\\033[38;5;<NUM>mText\\033[0m'   # Barva textu"
    echo "  echo -e '\\033[48;5;<NUM>mText\\033[0m'   # Barva pozadí"
    echo
    echo "Kde <NUM> je číslo 0-15 (nebo 0-255 v rozsahu 256-color palety)."
    echo "POZN.: 256-color režim (38;5/48;5) vyžaduje podporu terminálu."
    echo
}

main() {
    echo
    print_separator "16-Color Terminal Palette (Standardní barvy terminálu)"
    section_standard
    section_bright
    section_grid
    section_text
    section_usage
}

main "$@"
