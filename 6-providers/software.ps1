# Ukol 6.1 - seznam nainstalovaneho softwaru ze tri zdroju.
# Pouziva jen poskytovatele Registry, zadne WMI ani CIM.
# Zdroje:
#   1. HKLM Uninstall (64bit)
#   2. HKLM WOW6432Node Uninstall (32bit)
#   3. HKCU Uninstall (programy aktualniho uzivatele)
# Stejny nazev se ve vysledku objevi jen jednou.
# Spusteni: powershell -File .\software.ps1

$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$zdroje = @(
    @{
        Nazev = 'HKLM 64bit'
        Cesta = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'
    }
    @{
        Nazev = 'HKLM 32bit'
        Cesta = 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'
    }
    @{
        Nazev = 'HKCU'
        Cesta = 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'
    }
)

function Get-SoftwareFromUninstall {
    param(
        [string]$Path,
        [string]$Source
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return @()
    }

    foreach ($key in @(Get-ChildItem -LiteralPath $Path -ErrorAction SilentlyContinue)) {
        $props = Get-ItemProperty -LiteralPath $key.PSPath -ErrorAction SilentlyContinue
        $name = [string]$props.DisplayName
        if ([string]::IsNullOrWhiteSpace($name)) {
            continue
        }
        [pscustomobject]@{
            Nazev     = $name.Trim()
            Verze     = [string]$props.DisplayVersion
            Vydavatel = [string]$props.Publisher
            Zdroj     = $Source
        }
    }
}

$nalezeno = foreach ($zdroj in $zdroje) {
    Get-SoftwareFromUninstall -Path $zdroj.Cesta -Source $zdroj.Nazev
}
$nalezeno = @($nalezeno)

Write-Host 'Zdroje (Registry provider, bez WMI/CIM):'
foreach ($zdroj in $zdroje) {
    $pocet = @($nalezeno | Where-Object { $_.Zdroj -eq $zdroj.Nazev }).Count
    Write-Host ("  {0,-12} {1,4}  {2}" -f $zdroj.Nazev, $pocet, $zdroj.Cesta)
}

$jednou = $nalezeno |
    Group-Object { $_.Nazev.ToLowerInvariant() } |
    ForEach-Object {
        $_.Group |
            Sort-Object @{ Expression = { -not [string]::IsNullOrWhiteSpace($_.Verze) }; Descending = $true } |
            Select-Object -First 1
    } |
    Sort-Object Nazev

Write-Host ''
Write-Host ("Nalezeno celkem: {0}" -f $nalezeno.Count)
Write-Host ("Po odstraneni duplicit: {0}" -f @($jednou).Count)
Write-Host ''
$jednou | Format-Table -AutoSize Nazev, Verze, Vydavatel, Zdroj | Out-String -Width 200 | Write-Host
