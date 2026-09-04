#!/usr/bin/env bash
set -e

if [ ! -d ".venv" ]; then
    echo "[setup] criando ambiente virtual..."
    python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "[setup] instalando dependencias..."
python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements.txt

echo "[run] iniciando servidor..."
python -m app.web
