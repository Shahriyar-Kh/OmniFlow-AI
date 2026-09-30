[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$PullModel
)

$ErrorActionPreference = 'Stop'
$Model = 'qwen3:4b'
$Ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $Ollama) {
    Write-Host 'Ollama is not installed. Windows installation command:'
    Write-Host '  winget install --id Ollama.Ollama -e'
    Write-Host 'The qwen3:4b model download is substantial (approximately 2.5-3 GB).'
    if (-not $Install) {
        Write-Host 'Nothing was installed. Rerun with -Install only after approving the system change.'
        exit 2
    }
    winget install --id Ollama.Ollama -e
    if ($LASTEXITCODE -ne 0) { throw 'Ollama installation failed.' }
    $Ollama = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $Ollama) { throw 'Ollama installed but is not yet on PATH. Open a new terminal.' }
}

ollama --version
if ($PullModel) {
    Write-Host "Pulling $Model after explicit -PullModel request..."
    ollama pull $Model
    if ($LASTEXITCODE -ne 0) { throw "Could not pull $Model." }
} else {
    Write-Host "No model was downloaded. To approve the substantial download, run: ollama pull $Model"
}
