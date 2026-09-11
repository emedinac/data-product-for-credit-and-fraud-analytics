#!/usr/bin/env bash

set -euo pipefail

API_URL="${BACKEND_URL:-http://localhost:8000}"
DATA_ROOT="${DATA_ROOT:-raw_dev}"
RECORDS="${RECORDS:-10000}"
CUSTOMERS="${CUSTOMERS:-1000}"

echo "Creating batch..."
BATCH_ID="$({
  curl -fsS -X POST "$API_URL/v1/batches" \
    -H "Content-Type: application/json" \
    -d '{"source":"raw_dev"}'
} | poetry run python -c 'import json, sys; print(json.load(sys.stdin)["batch_id"])')"

echo "Batch: $BATCH_ID"

upload_file() {
  local file_path="$1"
  echo "Uploading $file_path..."
  curl -fsS -X POST "$API_URL/v1/batches/$BATCH_ID/files" \
    -F "file=@$file_path"
  echo
}

upload_file "$DATA_ROOT/customer_core/customers_00000.json"
upload_file "$DATA_ROOT/accounts/accounts_00000.csv"
upload_file "$DATA_ROOT/transactions/transactions_00000.jsonl"
upload_file "$DATA_ROOT/fraud/fraud_00000.jsonl"

echo "Processing batch..."
curl -fsS -X POST "$API_URL/v1/batches/$BATCH_ID/process"
echo

echo "Finished batch: $BATCH_ID"
