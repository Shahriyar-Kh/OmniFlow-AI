[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
docker compose ps

foreach ($Endpoint in @(
    'http://localhost:8080/health/live',
    'http://localhost:8080/health/ready',
    'http://localhost:8080/api/v1/system/status'
)) {
    try {
        $Result = Invoke-RestMethod -Uri $Endpoint -TimeoutSec 5
        $DisplayStatus = 'reachable'
        if ($null -ne $Result.status) { $DisplayStatus = $Result.status }
        Write-Host "$Endpoint -> $DisplayStatus"
    } catch {
        Write-Warning "$Endpoint -> unavailable"
    }
}
