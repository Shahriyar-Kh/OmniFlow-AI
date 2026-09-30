[CmdletBinding()]
param([datetime]$WeekStart)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
if (-not $WeekStart) { $Today = (Get-Date).Date; $WeekStart = $Today.AddDays(-(([int]$Today.DayOfWeek + 6) % 7)) }
$KeyLine = Get-Content -LiteralPath '.env' | Where-Object { $_ -like 'INTERNAL_API_KEY=*' } | Select-Object -First 1
if (-not $KeyLine) { throw 'INTERNAL_API_KEY is missing from .env.' }
$ApiKey = $KeyLine.Substring('INTERNAL_API_KEY='.Length)
$Body = @{ week_start = $WeekStart.ToString('yyyy-MM-dd'); language = 'roman_urdu' } | ConvertTo-Json
$Result = Invoke-RestMethod -Method Post -Uri 'http://localhost:8080/api/v1/plans/weekly' -Headers @{'X-TBOS-API-Key' = $ApiKey} -ContentType 'application/json' -Body $Body
Write-Host "Weekly plan $($Result.plan_id) contains $($Result.items.Count) unique slots; replay=$($Result.idempotent_replay)."
