#!/bin/bash

set -e
cd "$(dirname "$0")"

source .venv/bin/activate

# Create one output folder for both parts. The timestamp is in UTC.
output_dir="results/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p results
mkdir "$output_dir"

if [ "$1" = "1" ]; then
    python3 part1.py "$output_dir"
elif [ "$1" = "2" ]; then
    python3 part2.py "$output_dir"
else
    python3 part1.py "$output_dir" || echo "Part 1 failed. Continuing to Part 2."
    python3 part2.py "$output_dir"
fi
