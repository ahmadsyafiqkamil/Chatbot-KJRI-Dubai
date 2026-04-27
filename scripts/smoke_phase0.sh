#!/usr/bin/env bash
# smoke_phase0.sh — Verifikasi Phase 0 RAG infrastructure
# Jalankan: bash scripts/smoke_phase0.sh

set -euo pipefail

PASS=0
FAIL=0

ok()   { echo "[PASS] $1"; PASS=$((PASS + 1)); }
fail() { echo "[FAIL] $1"; FAIL=$((FAIL + 1)); }

echo "=== Phase 0 Smoke Check ==="
echo ""

# 1. Docker services
echo "-- 1. Docker services --"
if docker compose ps --format json 2>/dev/null | grep -q '"State":"running"'; then
    ok "docker compose services running"
else
    fail "docker compose services tidak running — jalankan: make start"
fi

# 2. PostgreSQL
echo ""
echo "-- 2. PostgreSQL --"
if docker exec kjri_postgres psql -U postgres -d rag_kjri -c "SELECT 1" > /dev/null 2>&1; then
    ok "PostgreSQL reachable"
else
    fail "PostgreSQL tidak reachable"
fi

# 3. pgvector extension
if docker exec kjri_postgres psql -U postgres -d rag_kjri -tAc "SELECT extname FROM pg_extension WHERE extname='vector'" 2>/dev/null | grep -q "vector"; then
    ok "pgvector extension aktif"
else
    fail "pgvector extension belum aktif"
fi

# 4. RAG tables
echo ""
echo "-- 3. RAG Tables --"
for tbl in documents document_chunks chat_history retrieval_analytics; do
    if docker exec kjri_postgres psql -U postgres -d rag_kjri -tAc \
        "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='$tbl')" 2>/dev/null | grep -q "t"; then
        ok "tabel '$tbl' ada"
    else
        fail "tabel '$tbl' MISSING"
    fi
done

# 5. ChromaDB
echo ""
echo "-- 4. ChromaDB --"
if curl -sf http://localhost:8001/api/v2/heartbeat > /dev/null 2>&1 || \
   curl -sf http://localhost:8001/api/v1/heartbeat > /dev/null 2>&1; then
    ok "ChromaDB reachable (port 8001)"
else
    fail "ChromaDB tidak reachable di http://localhost:8001"
fi

# 6. Insert/select sanity check
echo ""
echo "-- 5. Insert/Select sanity check --"
TEST_ID=$(docker exec kjri_postgres psql -U postgres -d rag_kjri -tAc \
    "INSERT INTO chat_history (session_id, role, content) VALUES ('smoke_test', 'user', 'hello phase0') RETURNING id" 2>/dev/null || echo "")
if [[ -n "$TEST_ID" ]]; then
    ok "INSERT chat_history berhasil (id: $TEST_ID)"
    docker exec kjri_postgres psql -U postgres -d rag_kjri -c \
        "DELETE FROM chat_history WHERE session_id='smoke_test'" > /dev/null 2>&1
else
    fail "INSERT chat_history gagal"
fi

# Summary
echo ""
echo "=========================="
echo "PASS: $PASS | FAIL: $FAIL"
if [[ $FAIL -eq 0 ]]; then
    echo "Phase 0: COMPLETE ✓"
else
    echo "Phase 0: INCOMPLETE — fix FAIL items di atas"
    exit 1
fi
