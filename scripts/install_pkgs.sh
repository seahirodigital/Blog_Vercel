#!/bin/bash

# Only run in remote environments (Claude Code on the web)
if [ "$CLAUDE_CODE_REMOTE" != "true" ]; then
  exit 0
fi

echo "Running remote environment setup..."

# TODO: Add your package installation commands here.
# For example:
# npm install
# pip install -r requirements.txt

exit 0
