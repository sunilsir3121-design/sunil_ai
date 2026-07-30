#!/usr/bin/env bash
# AppForge ko is computer par setup karta hai: local AI (Ollama) + CLI.
# Sab kuch offline/private rehta hai — koi API key nahi chahiye.
set -euo pipefail

MODEL="${APPFORGE_MODEL:-qwen2.5-coder:3b}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Ollama check"
if ! command -v ollama >/dev/null 2>&1; then
  echo "    Ollama install kar rahe hain..."
  curl -fsSL https://ollama.com/install.sh | sh
else
  echo "    pehle se installed: $(ollama --version)"
fi

echo "==> Ollama service"
if ! curl -sf http://localhost:11434/api/tags >/dev/null; then
  (ollama serve >/tmp/ollama.log 2>&1 &)
  for _ in $(seq 1 30); do
    curl -sf http://localhost:11434/api/tags >/dev/null && break
    sleep 1
  done
fi
curl -sf http://localhost:11434/api/tags >/dev/null || {
  echo "    Ollama start nahi hua — /tmp/ollama.log dekhein" >&2
  exit 1
}

echo "==> Model: $MODEL"
if ollama list | awk 'NR>1 {print $1}' | grep -qx "$MODEL"; then
  echo "    pehle se maujood"
else
  ollama pull "$MODEL"
fi

echo "==> AppForge CLI"
python3 -m pip install --user -e "$HERE"

echo
echo "Ho gaya. Ab chalayein:"
echo "  appforge --status"
echo '  appforge "ek todo app banao"'
