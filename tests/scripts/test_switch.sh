#!/usr/bin/env bash
set -e
BASE_URL="http://localhost:8000/api/v1"

echo "🔍 1. التحقق من جاهزية النظام قبل التبديل..."
curl -s -w "\nHTTP Status: %{http_code}\n" "$BASE_URL/ready" | jq

echo "🚀 2. إرسال طلب عبر HTTP مع إنشاء جلسة..."
SESSION_ID=$(python3 -c "import uuid; print(uuid.uuid4())")
curl -s -X POST "$BASE_URL/send" \
  -H "Content-Type: application/json" \
  -d "{\"protocol\": \"http\", \"session_id\": \"$SESSION_ID\", \"payload\": {\"action\": \"init\"}}" | jq

echo "🔄 3. التبديل الحي إلى WebSocket/GraphQL بنفس الجلسة..."
curl -s -X POST "$BASE_URL/send" \
  -H "Content-Type: application/json" \
  -d "{\"protocol\": \"graphql\", \"session_id\": \"$SESSION_ID\", \"payload\": {\"query\": \"{ status }\"}}" | jq

echo "✅ 4. التحقق من بقاء /ready أخضر أثناء التبديل..."
curl -s -w "\nHTTP Status: %{http_code}\n" "$BASE_URL/ready" | jq

echo "🔚 5. إغلاق الجلسة يدويًا..."
curl -s -X POST "$BASE_URL/close_session" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION_ID\", \"protocol\": \"graphql\"}" | jq

echo "✨ اكتمل سيناريو التبديل الحي بنجاح."