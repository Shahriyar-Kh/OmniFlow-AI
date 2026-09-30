[CmdletBinding()]
param(
    [ValidateSet('poster', 'reel')][string]$Type = 'poster',
    [string]$Topic,
    [ValidateSet('roman_urdu', 'simple_english')][string]$Language = 'roman_urdu'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$KeyLine = Get-Content -LiteralPath '.env' | Where-Object { $_ -like 'INTERNAL_API_KEY=*' } | Select-Object -First 1
if (-not $KeyLine) { throw 'INTERNAL_API_KEY is missing from .env.' }
$ApiKey = $KeyLine.Substring('INTERNAL_API_KEY='.Length)
$IsPoster = $Type -eq 'poster'
$ResolvedTopic = if ($Topic) { $Topic } elseif ($IsPoster) { 'What Is an API?' } else { 'Python List vs Tuple' }
$Pillar = if ($IsPoster) { 'Computer Science Concepts' } else { 'Python and Automation' }
$Audience = if ($IsPoster) { 'Beginner BS students' } else { 'Beginner Python learners' }
$Body = @{
    brief = @{
        content_type = $Type; topic = $ResolvedTopic; content_pillar = $Pillar
        target_audience = $Audience; objective = "Teach one clear concept about $ResolvedTopic"
        language = $Language; fact_sensitivity = 'LOW'
    }
    idempotency_key = "sample-$Type-$([guid]::NewGuid().ToString('N'))"
} | ConvertTo-Json -Depth 10
$Result = Invoke-RestMethod -Method Post -Uri 'http://localhost:8080/api/v1/content/generate' -Headers @{'X-TBOS-API-Key' = $ApiKey} -ContentType 'application/json' -Body $Body -TimeoutSec 600
Write-Host "Stored $Type content $($Result.content_id), version $($Result.version_number), QA $($Result.quality_report.score)."
