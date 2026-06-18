#!/usr/bin/env bash
# Run performance benchmarks against an ephemeral database.
# Usage: ./scripts/benchmark.sh [--count 10000]
set -euo pipefail

DB="/tmp/mintmory_bench_$(date +%s).db"
trap "rm -f $DB" EXIT

echo "Running MintMory Momento benchmark (db: $DB)..."
uv run python tests/benchmarks/momento_benchmark.py --db "$DB" "$@"
