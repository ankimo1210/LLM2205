#!/usr/bin/env bash
# test_chat.sh — smoke-test the local-chatgpt API
# Usage: bash scripts/test_chat.sh [conversation_id]
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
CONV_ID="${1:-}"

echo "=== Health check ==="
curl -sf "$BASE_URL/health"
echo

echo
echo "=== Conversations list ==="
curl -sf "$BASE_URL/conversations" | head -c 500
echo

echo
echo "=== Chat (SSE stream) ==="

PAYLOAD='{"message": "こんにちは！簡単に自己紹介してください。"}'
if [ -n "$CONV_ID" ]; then
  PAYLOAD="{\"conversation_id\": \"$CONV_ID\", \"message\": \"続きを教えてください。\"}"
fi

echo "→ POST $BASE_URL/chat"
echo "  payload: $PAYLOAD"
echo "──────────────────────────────────────────"

curl -sN \
  -X POST "$BASE_URL/chat" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" \
  --no-buffer

echo
echo "──────────────────────────────────────────"
echo "Done."
echo "Done."
