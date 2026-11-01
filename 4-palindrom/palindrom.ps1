# Ukol 4 - overeni, ze zadany text je palindrom.
# Ignoruje mezery, interpunkci, velikost pismen a diakritiku.
# Spusteni: powershell -File .\palindrom.ps1
#           powershell -File .\palindrom.ps1 "Jelenovi pivo nelej"

param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Text
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function ConvertTo-PalindromeKey {
    param([string]$Value)
    if ([string]::IsNullOrEmpty($Value)) {
        return ''
    }

    $formD = $Value.ToLowerInvariant().Normalize([System.Text.NormalizationForm]::FormD)
    $builder = New-Object System.Text.StringBuilder
    foreach ($ch in $formD.ToCharArray()) {
        $category = [System.Globalization.CharUnicodeInfo]::GetUnicodeCategory($ch)
        if ($category -eq [System.Globalization.UnicodeCategory]::NonSpacingMark) {
            continue
        }
        if ([char]::IsLetter($ch)) {
            [void]$builder.Append($ch)
        }
    }
    return $builder.ToString()
}

function Test-PalindromeText {
    param([string]$Value)
    $key = ConvertTo-PalindromeKey -Value $Value
    $chars = $key.ToCharArray()
    [array]::Reverse($chars)
    $reversed = -join $chars
    [pscustomobject]@{
        Text         = $Value
        Normalized   = $key
        IsPalindrome = ($key.Length -gt 0 -and $key -eq $reversed)
    }
}

function Write-PalindromeResult {
    param($Result)
    $verdikt = if ($Result.IsPalindrome) { 'JE palindrom' } else { 'NENÍ palindrom' }
    $barva = if ($Result.IsPalindrome) { 'Green' } else { 'Yellow' }
    Write-Host ''
    Write-Host ("Text: {0}" -f $Result.Text)
    Write-Host ("Po srovnání: {0}" -f $Result.Normalized)
    Write-Host ("Výsledek: {0}" -f $verdikt) -ForegroundColor $barva
}

$ukazky = @(
    @{ Text = 'Jelenovi pivo nelej'; MaByt = $true }
    @{ Text = 'Kobyla má malý bok'; MaByt = $true }
    @{ Text = 'Kupředu udeř puk'; MaByt = $true }
    @{ Text = 'Dal kopat Ota poklad'; MaByt = $true }
    @{ Text = 'Toto není palindrom'; MaByt = $false }
)

if ($Text -and $Text.Count -gt 0) {
    $vety = @(@{ Text = (($Text -join ' ').Trim()); MaByt = $null })
}
else {
    Write-Host 'Test vět ze zadání:'
    $vety = $ukazky
}

$shoda = 0
foreach ($veta in $vety) {
    $vysledek = Test-PalindromeText -Value $veta.Text
    Write-PalindromeResult -Result $vysledek
    if ($null -ne $veta.MaByt) {
        $ok = $vysledek.IsPalindrome -eq $veta.MaByt
        if ($ok) { $shoda++ }
        else { Write-Host '  Nesouhlasí s očekáváním ze zadání.' -ForegroundColor Red }
    }
}

Write-Host ''
if (-not $Text) {
    Write-Host ("Shoda se zadáním: {0} z {1}." -f $shoda, $vety.Count) -ForegroundColor Green
}
