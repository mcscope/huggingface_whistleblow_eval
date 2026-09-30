#!/bin/sh
set -e
python /seed.py
touch /tmp/seeded
echo "breakout board seeded"
tail -f /dev/null
