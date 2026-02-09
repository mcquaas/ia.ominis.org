#!/bin/bash
# Run taxonomy classification + batch reindex.
# Requires: .env configured, PostgreSQL running, Ollama running with ominis-2.0.
#
# Usage:
#   ./scripts/run_taxonomy_classification.sh [--dry-run] [--limit N]
#
# Then call batch-reindex via API (or run manually from admin UI).

set -e
cd "$(dirname "$0")/.."

# Activate venv if exists
if [ -d .venv ]; then
  source .venv/bin/activate
fi

echo "=== Step 1: Classify sources (LLM taxonomy extraction) ==="
python -m scripts.classify_rag_taxonomy "$@"

echo ""
echo "=== Step 2: Batch reindex (propagate taxonomy to chunks) ==="
echo "Call from admin or curl:"
echo "  POST /v1/api/rag-sources/batch-reindex"
echo "  Body: {\"onlyWithTaxonomy\": true, \"maxConcurrent\": 3}"
echo ""
echo "Or use the admin UI: trigger batch reindex from RAG sources."
