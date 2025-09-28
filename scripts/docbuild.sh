#!/bin/bash
# calls sphinx-autobuild

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Change to the parent directory
cd "$SCRIPT_DIR/.."

# Run sphinx-autobuild
sphinx-autobuild doc/source doc/build
