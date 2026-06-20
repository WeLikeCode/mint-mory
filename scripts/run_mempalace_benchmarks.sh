#!/usr/bin/env bash
# Reproduce the MintMory × mempalace agent-memory benchmark suite (BENCHMARKS.md).
#
# Each harness ingests a conversational dataset into a MintMory store and measures
# retrieval recall with the SAME metric + embedder (all-MiniLM-L6-v2) the
# competitor uses, printing MintMory's vector / hybrid / weighted-hybrid variants
# next to the published baseline. Datasets are fetched on first run.
#
# Usage:
#   uv sync --extra local          # install the MiniLM embedder first
#   ./scripts/run_mempalace_benchmarks.sh            # all four
#   ./scripts/run_mempalace_benchmarks.sh longmemeval locomo   # a subset
set -euo pipefail

RUN=${RUN:-"uv run --no-sync python"}
WHICH=("$@")
[ ${#WHICH[@]} -eq 0 ] && WHICH=(longmemeval locomo convomem membench)

has() { for x in "${WHICH[@]}"; do [ "$x" = "$1" ] && return 0; done; return 1; }

if has longmemeval; then
  echo "==== LongMemEval (500 q) ===="
  LME=/tmp/lme-data/longmemeval_s_cleaned.json
  if [ ! -f "$LME" ]; then mkdir -p /tmp/lme-data
    curl -fsSL -o "$LME" \
      https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main/longmemeval_s_cleaned.json
  fi
  $RUN docs/eval/mempalace_longmemeval_benchmark.py "$LME"
fi

if has locomo; then
  echo "==== LoCoMo (1,986 q) ===="
  [ -d /tmp/locomo ] || git clone --depth 1 https://github.com/snap-research/locomo.git /tmp/locomo
  $RUN docs/eval/mempalace_locomo_benchmark.py /tmp/locomo/data/locomo10.json
fi

if has convomem; then
  echo "==== ConvoMem (250) ===="
  $RUN docs/eval/mempalace_convomem_benchmark.py --limit 50
fi

if has membench; then
  echo "==== MemBench (8,500) ===="
  [ -d /tmp/membench ] || git clone --depth 1 https://github.com/import-myself/Membench.git /tmp/membench
  $RUN docs/eval/mempalace_membench_benchmark.py /tmp/membench/MemData/FirstAgent
fi

echo "Done. Per-benchmark JSON written under docs/eval/*_results.json"
