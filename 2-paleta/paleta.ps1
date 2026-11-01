# Ukol 2 - 16 prednastavenych barev konzole.
# Tri sloupce: nazev, nazev barvou pisma, nazev na barevnem pozadi.
# Poradi je [enum]::GetValues([System.ConsoleColor]).
# Spusteni: powershell -File .\paleta.ps1

$barvy = [enum]::GetValues([System.ConsoleColor])
foreach ($barva in $barvy) {
    $nazev = '{0,-16}' -f $barva
    Write-Host $nazev -NoNewline
    Write-Host $nazev -ForegroundColor $barva -NoNewline
    Write-Host $nazev -BackgroundColor $barva
}
