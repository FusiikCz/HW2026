# Ukol 2 - paleta 16 odstinu barev prednastavenych v terminalu.
# Dva radky po osmi: 0-7 standardni, 8-15 jasne.
# Spusteni: powershell -File .\paleta.ps1

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# Poradi je ANSI paleta 0-15, namapovana na barvy Windows konzole.
$barvy = @(
    @{ Id = 0;  Bg = 'Black';       Fg = 'White'; Nazev = 'Black';          Cesky = 'černá' }
    @{ Id = 1;  Bg = 'DarkRed';      Fg = 'White'; Nazev = 'Red';            Cesky = 'červená' }
    @{ Id = 2;  Bg = 'DarkGreen';    Fg = 'White'; Nazev = 'Green';          Cesky = 'zelená' }
    @{ Id = 3;  Bg = 'DarkYellow';   Fg = 'Black'; Nazev = 'Yellow';         Cesky = 'žlutá' }
    @{ Id = 4;  Bg = 'DarkBlue';     Fg = 'White'; Nazev = 'Blue';           Cesky = 'modrá' }
    @{ Id = 5;  Bg = 'DarkMagenta';  Fg = 'White'; Nazev = 'Magenta';        Cesky = 'purpurová' }
    @{ Id = 6;  Bg = 'DarkCyan';     Fg = 'Black'; Nazev = 'Cyan';           Cesky = 'azurová' }
    @{ Id = 7;  Bg = 'Gray';         Fg = 'Black'; Nazev = 'White';          Cesky = 'bílá' }
    @{ Id = 8;  Bg = 'DarkGray';     Fg = 'White'; Nazev = 'Bright Black';   Cesky = 'jasná černá' }
    @{ Id = 9;  Bg = 'Red';          Fg = 'White'; Nazev = 'Bright Red';     Cesky = 'jasná červená' }
    @{ Id = 10; Bg = 'Green';        Fg = 'Black'; Nazev = 'Bright Green';   Cesky = 'jasná zelená' }
    @{ Id = 11; Bg = 'Yellow';       Fg = 'Black'; Nazev = 'Bright Yellow';  Cesky = 'jasná žlutá' }
    @{ Id = 12; Bg = 'Blue';         Fg = 'White'; Nazev = 'Bright Blue';    Cesky = 'jasná modrá' }
    @{ Id = 13; Bg = 'Magenta';      Fg = 'White'; Nazev = 'Bright Magenta'; Cesky = 'jasná purpurová' }
    @{ Id = 14; Bg = 'Cyan';         Fg = 'Black'; Nazev = 'Bright Cyan';    Cesky = 'jasná azurová' }
    @{ Id = 15; Bg = 'White';        Fg = 'Black'; Nazev = 'Bright White';   Cesky = 'jasná bílá' }
)

function Write-Swatch {
    param(
        [hashtable]$Barva,
        [int]$Width = 6
    )
    $label = '{0,2}' -f $Barva.Id
    $pad = [Math]::Max(0, $Width - $label.Length)
    $left = [Math]::Floor($pad / 2)
    $right = $pad - $left
    $text = (' ' * $left) + $label + (' ' * $right)
    Write-Host $text -BackgroundColor $Barva.Bg -ForegroundColor $Barva.Fg -NoNewline
}

Write-Host ''
Write-Host 'Paleta 16 odstínů barev přednastavených v terminálu'
Write-Host ''

Write-Host 'Standardní (0-7)'
Write-Host -NoNewline '  '
foreach ($barva in $barvy[0..7]) {
    Write-Swatch -Barva $barva
    Write-Host -NoNewline ' '
}
Write-Host ''
Write-Host ''

Write-Host 'Jasné (8-15)'
Write-Host -NoNewline '  '
foreach ($barva in $barvy[8..15]) {
    Write-Swatch -Barva $barva
    Write-Host -NoNewline ' '
}
Write-Host ''
Write-Host ''

Write-Host 'Číslo  Název              Česky               Ukázka'
Write-Host '-----  -----------------  ------------------  ------'
foreach ($barva in $barvy) {
    Write-Host ('{0,5}  {1,-17}  {2,-18}  ' -f $barva.Id, $barva.Nazev, $barva.Cesky) -NoNewline
    Write-Host '      ' -BackgroundColor $barva.Bg -ForegroundColor $barva.Fg
}

Write-Host ''
Write-Host 'Použití v PowerShellu:'
Write-Host "  Write-Host 'text' -ForegroundColor Yellow"
Write-Host "  Write-Host 'text' -BackgroundColor DarkBlue -ForegroundColor White"
Write-Host ''
