#!/bin/bash
QT_QPA_PLATFORM=offscreen
export QT_QPA_PLATFORM
CI=True
export CI

find . -name "*.pyc" -exec rm -f {} \;
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
# python3 scripts/setup_repository.py
python3 -m coverage run -m unittest discover -s tests
python3 -m coverage report