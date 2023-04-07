#!/bin/bash
export QT_QPA_PLATFORM=offscreen
export CI=True
pytest --no-cov-on-fail