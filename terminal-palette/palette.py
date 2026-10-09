#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Terminal 16-Color Palette Viewer
Vykreslí paletu 16 standardních barev přednastavených v terminálu
"""

def print_separator(title):
    """Vytiskne ozdobný oddělovač"""
    print("╔" + "═" * 75 + "╗")
    print("║" + title.center(75) + "║")
    print("╚" + "═" * 75 + "╝")
    print()

def main():
    # Názvy barev
    color_names = [
        "Black",           # 0
        "Red",             # 1
        "Green",           # 2
        "Yellow",          # 3
        "Blue",            # 4
        "Magenta",         # 5
        "Cyan",            # 6
        "White",           # 7
        "Bright Black",    # 8
        "Bright Red",      # 9
        "Bright Green",    # 10
        "Bright Yellow",   # 11
        "Bright Blue",     # 12
        "Bright Magenta",  # 13
        "Bright Cyan",     # 14
        "Bright White"     # 15
    ]
    
    print()
    print_separator("16-Color Terminal Palette (Standardní barvy terminálu)")
    
    # Část 1: Standardní barvy (0-7)
    print("Standardní barvy (0-7):\n")
    for i in range(8):
        bg_color = f"\033[48;5;{i}m"
        fg_color = f"\033[38;5;{i}m"
        reset = "\033[0m"
        print(f"{bg_color}  {i:2d}  {reset}  {fg_color}{color_names[i]}{reset}")
    
    # Část 2: Jasné barvy (8-15)
    print("\nJasné barvy (8-15):\n")
    for i in range(8, 16):
        bg_color = f"\033[48;5;{i}m"
        fg_color = f"\033[38;5;{i}m"
        reset = "\033[0m"
        print(f"{bg_color}  {i:2d}  {reset}  {fg_color}{color_names[i]}{reset}")
    
    # Část 3: Tabulka
    print()
    print_separator("Náhled barev v mřížce")
    
    print("Mřížka 4x4:\n")
    for row in range(4):
        for col in range(4):
            color = row * 4 + col
            bg_color = f"\033[48;5;{color}m"
            reset = "\033[0m"
            print(f"{bg_color}   {color:2d}   {reset}", end="")
        print()
    
    # Část 4: Barevný text
    print()
    print_separator("Jednotlivé barvy s textem")
    
    print()
    for i in range(16):
        bg_color = f"\033[48;5;{i}m"
        fg_white = f"\033[38;5;7m"
        reset = "\033[0m"
        print(f"{bg_color}{fg_white} Color {i:2d} {reset}", end="")
        if (i + 1) % 4 == 0:
            print()
    
    # Část 5: Pokyny na použití
    print()
    print()
    print_separator("Použití barev ve vašich skriptech a programech")
    
    print()
    print("Python:")
    print("  print('\\033[38;5;<NUM>mText\\033[0m')  # Barva textu")
    print("  print('\\033[48;5;<NUM>mText\\033[0m')  # Barva pozadí")
    print()
    print("Bash:")
    print("  echo -e '\\033[38;5;<NUM>mText\\033[0m'   # Barva textu")
    print("  echo -e '\\033[48;5;<NUM>mText\\033[0m'   # Barva pozadí")
    print()
    print("Kde <NUM> je číslo 0-15 (nebo 0-255 v rozsahu 256-color palety)")
    print()

if __name__ == "__main__":
    main()
