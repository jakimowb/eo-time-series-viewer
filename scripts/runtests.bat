#!/bin/bash
set QT_QPA_PLATFORM=offscreen
set CI=True
pytest --no-cov-on-fail --cov-config=%CD%\.coveragec