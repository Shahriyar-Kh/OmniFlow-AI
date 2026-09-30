[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
function Get-LocalSetting([string]$Name, [string]$Default) {
    $Line = Get-Content -LiteralPath '.env' | Where-Object { $_ -like "$Name=*" } | Select-Object -First 1
    if (-not $Line) { return $Default }
    return $Line.Substring($Name.Length + 1)
}
$Model = Get-LocalSetting 'OLLAMA_MODEL' 'qwen3:4b'
$BaseUrl = 'http://localhost:11434'
try { $Tags = Invoke-RestMethod -Uri "$BaseUrl/api/tags" -TimeoutSec 5 } catch {
    throw 'Ollama is not reachable at http://localhost:11434. Start or install Ollama first.'
}
if ($Model -notin @($Tags.models.name)) { throw "Selected model is unavailable: $Model" }
$TextBody = @{ model = $Model; prompt = 'Reply with only: OK'; stream = $false } | ConvertTo-Json
$Text = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/generate" -ContentType 'application/json' -Body $TextBody -TimeoutSec 180
if (-not $Text.response) { throw 'Basic Ollama generation failed.' }
$JsonBody = @{
    model = $Model
    prompt = 'Return strict JSON: {"concept":"API","roman_urdu":"API apps ko connect karti hai"}'
    stream = $false
    format = 'json'
} | ConvertTo-Json
$Json = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/generate" -ContentType 'application/json' -Body $JsonBody -TimeoutSec 180
$Parsed = $Json.response | ConvertFrom-Json
if (-not $Parsed.concept -or -not $Parsed.roman_urdu) { throw 'Strict JSON or Roman Urdu generation failed.' }
docker compose exec -T renderer-api python -c "import urllib.request; urllib.request.urlopen('http://host.docker.internal:11434/api/tags', timeout=5)"
if ($LASTEXITCODE -ne 0) { throw 'Container-to-host Ollama connectivity failed.' }
Write-Host "Ollama live checks passed for $Model."
