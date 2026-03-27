#!/bin/bash

# リモート環境でのみ実行
if [ "$CLAUDE_CODE_REMOTE" != "true" ]; then
  exit 0
fi

echo "Running remote environment setup..."

# Node.js依存のインストール
npm install

# Python依存のインストール
pip install -r scripts/pipeline/requirements.txt

exit 0
