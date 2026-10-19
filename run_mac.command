#!/bin/zsh
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
  echo "Creating Python environment..."
  python3 -m venv .venv || exit 1
fi

source .venv/bin/activate
DEPS_MARKER=".venv/.cnc_analyzer_deps_v1_1_0"
if [ ! -f "$DEPS_MARKER" ]; then
  echo "Installing/updating analyzer dependencies..."
  python -m pip install --upgrade pip || exit 1
  python -m pip install -r requirements.txt || exit 1
  touch "$DEPS_MARKER"
fi

python -m streamlit run app.py
