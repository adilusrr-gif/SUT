#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then python3 deploy/init_env.py; fi
docker compose up -d --build db backend frontend
echo 'Süt started on loopback. See README for SSH forwarding and optional Ollama.'
docker compose ps
