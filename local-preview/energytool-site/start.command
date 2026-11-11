#!/bin/zsh
cd -- "$(dirname -- "$0")"
(sleep 1; open 'http://127.0.0.1:8767') &
python3 serve.py
