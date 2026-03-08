#!/usr/bin/env bash
# test_chat.sh — smoke-test the /chat SSE endpoint
# Usage: bash scripts/test_chat.sh [conversation_id]
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
CONV_ID="${1:-}"

PAYLOAD="{\"message\": \"こんにちは！簡単に自己紹介してください。\"}"
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
