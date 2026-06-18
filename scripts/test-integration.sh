#!/usr/bin/env bash
# Run M1 integration tests against a temporary database.
# Usage: ./scripts/test-integration.sh [--db /path/to/test.db]
set -euo pipefail

DB=${MINTMORY_DB:-"/tmp/mintmory_integration_test.db"}
rm -f "$DB"

echo "Running integration tests (db: $DB)..."
MINTMORY_DB="$DB" uv run pytest tests/integration/ -v --no-cov "$@"
EXIT_CODE=$?
rm -f "$DB"
exit $EXIT_CODE
