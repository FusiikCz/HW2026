# Ukol 5 - vsechny tri body pres CIM (Get-CimInstance / Get-CimClass / Set-CimInstance).
# U uctu je vedle CIM i Get-LocalUser, aby slo oba postupy porovnat.
# Spusteni: powershell -File .\reseni.ps1

$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function Write-Hlavicka {
    param([string]$Text)
    Write-Host ''
    Write-Host $Text -ForegroundColor Cyan
}

Write-Hlavicka '1. Trida pro spravu tiskaren: Win32_Printer'
$vlastnosti = (Get-CimClass -ClassName Win32_Printer).CimClassProperties |
    Select-Object Name, CimType
$vlastnosti | Format-Table -AutoSize | Out-String -Width 80 | Write-Host
Write-Host ("Pocet vlastnosti: {0}" -f @($vlastnosti).Count)

Write-Host ''
Write-Host 'Instalovane tiskarny:'
Get-CimInstance -ClassName Win32_Printer |
    Select-Object Name, Location, PortName |
    Format-Table -AutoSize |
    Out-String -Width 120 |
    Write-Host

$faxy = @(Get-CimInstance -ClassName Win32_Printer | Where-Object { $_.Name -match '(?i)fax' })
if ($faxy.Count -eq 0) {
    Write-Host 'Tiskarna s nazvem Fax na tomhle pocitaci neni, umisteni se proto nemeni.'
}
else {
    foreach ($fax in $faxy) {
        $puvodni = [string]$fax.Location
        $nove = 'HW2026'
        Write-Host ("Fax '{0}': umisteni '{1}' -> '{2}'" -f $fax.Name, $puvodni, $nove)
        Set-CimInstance -InputObject $fax -Property @{ Location = $nove } | Out-Null
        $po = Get-CimInstance -ClassName Win32_Printer -Filter ("Name='{0}'" -f $fax.Name.Replace("'", "''"))
        Write-Host ("Po zmene: '{0}'" -f $po.Location)
    }
}

Write-Hlavicka '2. Nazev disku C:'
$logicky = Get-CimInstance -ClassName Win32_LogicalDisk -Filter "DeviceID='C:'"
$svazek = Get-CimInstance -ClassName Win32_Volume -Filter "DriveLetter='C:'"
Write-Host ("Win32_LogicalDisk.VolumeName = {0}" -f $logicky.VolumeName)
Write-Host ("Win32_Volume.Label           = {0}" -f $svazek.Label)

$puvodniPopisek = [string]$svazek.Label
if ($puvodniPopisek -eq 'System') {
    Write-Host 'Disk C: uz se jmenuje System, prejmenovani neni potreba.'
}
else {
    Write-Host ("Prejmenovavam popisek '{0}' na 'System'." -f $puvodniPopisek)
    try {
        Set-CimInstance -InputObject $svazek -Property @{ Label = 'System' } -ErrorAction Stop | Out-Null
        $poDisku = Get-CimInstance -ClassName Win32_Volume -Filter "DriveLetter='C:'"
        Write-Host ("Novy popisek: {0}" -f $poDisku.Label) -ForegroundColor Green
    }
    catch {
        $zustal = (Get-CimInstance -ClassName Win32_Volume -Filter "DriveLetter='C:'").Label
        Write-Host 'Prejmenovani se nepovedlo. Set-CimInstance na Win32_Volume chce zvysena prava.' -ForegroundColor Yellow
        Write-Host $_.Exception.Message
        Write-Host ("Spustte tento skript v PowerShellu jako spravce. Popisek zustava '{0}'." -f $zustal)
    }
}

Write-Hlavicka '3a. Ucty pres Get-LocalUser'
Write-Host 'Get-LocalUser ma LastLogon, nema vlastnost Lockout.'
$localni = @(Get-LocalUser)
$localni | Select-Object Name, Enabled, LastLogon | Format-Table -AutoSize | Out-String -Width 120 | Write-Host
$nikdyLocal = @($localni | Where-Object { $null -eq $_.LastLogon })
Write-Host ("Ucty s prazdnym LastLogon: {0}" -f (($nikdyLocal.Name) -join ', '))
Write-Host 'Na tomhle pocitaci je LastLogon prazdny i u uctu, ktery se pouziva. Sam Get-LocalUser proto nepouzity ucet spolehlive nepozna.'

Write-Hlavicka '3b. Ucty pres CIM'
Write-Host 'Win32_UserAccount ma Lockout a Disabled, nema LastLogon.'
$cimUcty = @(Get-CimInstance -ClassName Win32_UserAccount -Filter 'LocalAccount=True')
$cimUcty | Select-Object Name, Disabled, Lockout, Status | Format-Table -AutoSize | Out-String -Width 120 | Write-Host

$uzamcene = @($cimUcty | Where-Object { $_.Lockout })
if ($uzamcene.Count -eq 0) {
    Write-Host 'Uzamcene ucty (Lockout=True): zadne.'
}
else {
    Write-Host ("Uzamcene ucty: {0}" -f (($uzamcene.Name) -join ', '))
}

Write-Host ''
Write-Host 'Kdo se skutecne prihlasil, rika Win32_UserProfile.LastUseTime (ne sitovy profil).'
$profily = @(Get-CimInstance -ClassName Win32_UserProfile | Where-Object {
    -not $_.Special -and $_.LocalPath -like 'C:\Users\*'
})
$profily | Select-Object @{ n = 'Ucet'; e = { Split-Path $_.LocalPath -Leaf } }, LastUseTime, Loaded |
    Format-Table -AutoSize |
    Out-String -Width 120 |
    Write-Host

$pouzitaJmena = @($profily | ForEach-Object { Split-Path $_.LocalPath -Leaf })
$nepouzite = @($cimUcty | Where-Object { $_.Name -notin $pouzitaJmena })
Write-Host ("Ucty bez prihlaseni (zadny profil v C:\Users): {0}" -f (($nepouzite.Name) -join ', '))

Write-Host ''
Write-Host 'Porovnani: Get-LocalUser ukaze Enabled a LastLogon, ale Lockout neumi a prazdny LastLogon tu ma i pouzivany ucet.' -ForegroundColor Green
Write-Host 'CIM Win32_UserAccount ukaze Lockout. Kdo se nikdy neprihlasil, doplni Win32_UserProfile.' -ForegroundColor Green
Write-Host ''
