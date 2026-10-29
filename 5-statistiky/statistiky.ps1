# Ukol 5 - statistika textu predaneho v terminalu.
# Na strance se zadanim tento ukol nema cislo.
# Vypise pocet znaku s mezerami, bez mezer, pocet samohlasek a pocet slov.
#
#   powershell -File .\statistiky.ps1 "Jelenovi pivo nelej"
#   powershell -File .\statistiky.ps1

param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Text
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

if ($Text -and $Text.Count -gt 0) {
    $vstup = ($Text -join ' ').Trim()
}
else {
    $vstup = Read-Host 'Zadejte text'
}

$samohlasky = 'aeiouyáéěíóúůý'
$pocetSamohlasek = 0
foreach ($ch in $vstup.ToCharArray()) {
    if ($samohlasky.IndexOf(([string]$ch).ToLowerInvariant()) -ge 0) {
        $pocetSamohlasek++
    }
}

$bezMezer = ($vstup -replace ' ', '')
$slova = @($vstup -split '\s+' | Where-Object { $_ -ne '' })

Write-Host ''
Write-Host ("Text: {0}" -f $vstup)
Write-Host ("Znaky s mezerami:  {0}" -f $vstup.Length)
Write-Host ("Znaky bez mezer:   {0}" -f $bezMezer.Length)
Write-Host ("Samohlásky:        {0}" -f $pocetSamohlasek)
Write-Host ("Slova:             {0}" -f $slova.Count)
Write-Host ''
