#!/bin/sh
set -e
python /seed.py
touch /tmp/seeded
echo "devlog seeding complete"
tail -f /dev/null
