# Ukol 3 - aliasy np (notepad.exe) a ct (control.exe).
# Vytvori je, zalohuje do JSON a XML, smaze, obnovi z JSON,
# znovu smaze a obnovi z XML.
# Spusteni: powershell -File .\aliasy.ps1

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$jsonPath = Join-Path $scriptDir 'aliasy.json'
$xmlPath = Join-Path $scriptDir 'aliasy.xml'

$definice = @(
    @{ Name = 'np'; Value = 'notepad.exe' }
    @{ Name = 'ct'; Value = 'control.exe' }
)

function Write-Step {
    param([string]$Text)
    Write-Host ''
    Write-Host $Text -ForegroundColor Cyan
}

function Set-HomeworkAlias {
    param(
        [string]$Name,
        [string]$Value
    )
    if ($Name -notin @('np', 'ct')) {
        throw "Neplatný název aliasu: $Name"
    }
    Set-Alias -Name $Name -Value $Value -Scope Global -Force
}

function Remove-HomeworkAlias {
    param([string]$Name)
    $existing = Get-Alias -Name $Name -Scope Global -ErrorAction SilentlyContinue
    if (-not $existing) {
        return
    }
    Remove-Item -LiteralPath "Alias:\$Name" -Force
}

function Show-HomeworkAliases {
    foreach ($item in $definice) {
        $alias = Get-Alias -Name $item.Name -Scope Global -ErrorAction SilentlyContinue
        if ($alias) {
            Write-Host ("  {0} -> {1}" -f $alias.Name, $alias.Definition)
        }
        else {
            Write-Host ("  {0} -> (smazaný)" -f $item.Name)
        }
    }
}

function Assert-HomeworkAliases {
    param([bool]$ShouldExist)
    foreach ($item in $definice) {
        $alias = Get-Alias -Name $item.Name -Scope Global -ErrorAction SilentlyContinue
        $exists = [bool]$alias
        if ($exists -ne $ShouldExist) {
            $stav = if ($ShouldExist) { 'chybí' } else { 'pořád existuje' }
            throw ("Alias {0} {1}." -f $item.Name, $stav)
        }
        if ($ShouldExist -and [string]$alias.Definition -ne [string]$item.Value) {
            throw ("Alias {0} vede na {1}, očekáváno {2}." -f $alias.Name, $alias.Definition, $item.Value)
        }
    }
}

function Export-HomeworkAliases {
    $items = foreach ($item in $definice) {
        $alias = Get-Alias -Name $item.Name -Scope Global
        [pscustomobject]@{
            Name  = [string]$alias.Name
            Value = [string]$alias.Definition
        }
    }

    $json = ($items | ConvertTo-Json -Depth 3).Trim() + [Environment]::NewLine
    [System.IO.File]::WriteAllText($jsonPath, $json, (New-Object System.Text.UTF8Encoding $false))

    $settings = New-Object System.Xml.XmlWriterSettings
    $settings.Indent = $true
    $settings.Encoding = New-Object System.Text.UTF8Encoding $false
    $writer = [System.Xml.XmlWriter]::Create($xmlPath, $settings)
    try {
        $writer.WriteStartDocument()
        $writer.WriteStartElement('Aliases')
        foreach ($item in $items) {
            $writer.WriteStartElement('Alias')
            $writer.WriteAttributeString('Name', $item.Name)
            $writer.WriteAttributeString('Value', $item.Value)
            $writer.WriteEndElement()
        }
        $writer.WriteEndElement()
        $writer.WriteEndDocument()
    }
    finally {
        $writer.Close()
    }
}

function Import-HomeworkAliasesFromJson {
    param([string]$Path)
    # V PS 5.1 nesmi byt vysledek ConvertFrom-Json znovu zabaleny do @().
    # Jinak se pole dvou aliasu slozi do jednoho nazvu "np ct".
    $raw = [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
    $parsed = $raw | ConvertFrom-Json
    foreach ($item in $parsed) {
        Set-HomeworkAlias -Name ([string]$item.Name) -Value ([string]$item.Value)
    }
}

function Import-HomeworkAliasesFromXml {
    param([string]$Path)
    $xml = New-Object System.Xml.XmlDocument
    $xml.Load($Path)
    foreach ($node in $xml.SelectNodes('/Aliases/Alias')) {
        Set-HomeworkAlias -Name $node.GetAttribute('Name') -Value $node.GetAttribute('Value')
    }
}

Write-Step '1. Vytvoření aliasů np a ct'
foreach ($item in $definice) {
    Set-HomeworkAlias -Name $item.Name -Value $item.Value
}
Show-HomeworkAliases
Assert-HomeworkAliases -ShouldExist $true

Write-Step '2. Záloha do JSON a do XML'
Export-HomeworkAliases
Write-Host "  JSON: $jsonPath"
Write-Host "  XML:  $xmlPath"
Write-Host ''
Write-Host '--- aliasy.json ---'
Get-Content -LiteralPath $jsonPath
Write-Host '--- aliasy.xml ---'
Get-Content -LiteralPath $xmlPath

Write-Step '3. Smazání obou aliasů'
foreach ($item in $definice) {
    Remove-HomeworkAlias -Name $item.Name
}
Show-HomeworkAliases
Assert-HomeworkAliases -ShouldExist $false

Write-Step '4. Obnova z JSON'
Import-HomeworkAliasesFromJson -Path $jsonPath
Show-HomeworkAliases
Assert-HomeworkAliases -ShouldExist $true

Write-Step '5. Znovu smazání obou aliasů'
foreach ($item in $definice) {
    Remove-HomeworkAlias -Name $item.Name
}
Show-HomeworkAliases
Assert-HomeworkAliases -ShouldExist $false

Write-Step '6. Obnova z XML'
Import-HomeworkAliasesFromXml -Path $xmlPath
Show-HomeworkAliases
Assert-HomeworkAliases -ShouldExist $true

Write-Host ''
Write-Host 'Hotovo. Aliasy np a ct jsou obnovené z XML a platí v této relaci.' -ForegroundColor Green
Write-Host 'Ověření:  np  otevře Poznámkový blok,  ct  otevře Ovládací panely.'
Write-Host ''
