#!/bin/bash
# Doble clic en Finder (o ./actualizar.command) para actualizar el dashboard con la última información.
cd "$(dirname "$0")"
if [ -x .venv/bin/python ]; then PY=.venv/bin/python; else PY=python3; fi
"$PY" actualizar.py
echo
read -n 1 -s -r -p "Presiona cualquier tecla para cerrar..."
