#!/usr/bin/env bash
set -euo pipefail
model="qwen3:4b"
if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama is not installed. On Windows PowerShell run:"
  echo "  winget install --id Ollama.Ollama -e"
  echo "The $model model download is substantial (approximately 2.5-3 GB)."
  echo "Nothing was installed or downloaded."
  exit 2
fi
ollama --version
echo "No model was downloaded. After explicit approval run: ollama pull $model"
