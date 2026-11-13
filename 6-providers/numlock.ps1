# Ukol 6.2 - NumLock pred prihlasenim uzivatele.
# Stav je v registru vychoziho profilu, ktery plati na prihlasovaci obrazovce.
# Bit 2 (hodnota 2) znamena NumLock. Windows 10/11 si zapnuty NumLock
# uklada taky jako 2147483648. Kdyz neni zapnuty, skript nastavi hodnotu 2.
# Spusteni: powershell -File .\numlock.ps1

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$cesta = 'Registry::HKEY_USERS\.DEFAULT\Control Panel\Keyboard'
$jmeno = 'InitialKeyboardIndicators'

function Test-NumLockZapnuty {
    param($Value)
    $cislo = 0L
    if (-not [int64]::TryParse([string]$Value, [ref]$cislo)) {
        return $false
    }
    if ($cislo -eq 2147483648) {
        return $true
    }
    return (($cislo -band 2) -eq 2)
}

$aktualni = (Get-ItemProperty -LiteralPath $cesta -Name $jmeno).$jmeno
$zapnuto = Test-NumLockZapnuty -Value $aktualni

Write-Host "Klic: $cesta"
Write-Host "InitialKeyboardIndicators = $aktualni"

if ($zapnuto) {
    Write-Host 'NumLock pred prihlasenim je zapnuty. Zmena neni potreba.' -ForegroundColor Green
}
else {
    Write-Host 'NumLock pred prihlasenim je vypnuty. Nastavuji hodnotu 2.' -ForegroundColor Yellow
    Set-ItemProperty -LiteralPath $cesta -Name $jmeno -Value '2'
    $po = (Get-ItemProperty -LiteralPath $cesta -Name $jmeno).$jmeno
    Write-Host "Nova hodnota: $po" -ForegroundColor Green
}
