[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
& "$PSScriptRoot/verify.ps1"
$Topics = Invoke-RestMethod -Uri 'http://localhost:8080/api/v1/topics'
if ($Topics.total -lt 70) { throw 'Topic library contains fewer than 70 active topics.' }
$Unauthorized = $null
try { Invoke-WebRequest -Method Post -Uri 'http://localhost:8080/api/v1/plans/weekly' -ContentType 'application/json' -Body '{"week_start":"2026-09-21"}' -UseBasicParsing | Out-Null } catch { $Unauthorized = $_.Exception.Response.StatusCode.value__ }
if ($Unauthorized -ne 401) { throw 'Mutation endpoint did not reject a missing internal API key.' }
$PromptCount = 'SELECT count(*) FROM prompt_templates WHERE is_active = true;' | docker compose exec -T postgres sh -c 'psql -U $APP_DB_USER -d $APP_DB_NAME -tA'
if ([int]$PromptCount.Trim() -lt 7) { throw 'Seven active prompt templates were not synchronized.' }
$AiStatus = Invoke-RestMethod -Uri 'http://localhost:8080/api/v1/ai/status'
if (-not $AiStatus.selected_model) { throw 'AI status response is invalid.' }
Write-Host "Phase 02 implementation verification passed. Ollama reachable=$($AiStatus.reachable), model_available=$($AiStatus.model_available)."
