#!/usr/bin/env python3
"""
seed_embeddings.py — Generate and store vector embeddings for layanan_konsuler.

Embeds a combined text of nama_pelayanan + syarat (wajib + kondisional) per row
using Gemini gemini-embedding-001 (RETRIEVAL_DOCUMENT task type), then stores
the result in the embedding column.

Requirements:
    pip install psycopg2-binary google-genai python-dotenv

Environment:
    GEMINI_API_KEY — required before calling the API (skipped if early exit via
        SEED_EMBEDDINGS_SKIP_IF_FULL when every row already has an embedding).
    SEED_EMBEDDINGS_SKIP_IF_FULL — if truthy ("1", "true", "yes"): if all rows
        in layanan_konsuler already have embedding IS NOT NULL, exit 0 without
        API calls.

Usage:
    python scripts/seed_embeddings.py
"""

import json
import os
import sys
import time

import psycopg2
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "postgres")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "rag_kjri")

EMBEDDING_MODEL = "gemini-embedding-001"
BATCH_DELAY = 0.5  # seconds between API calls to avoid rate limiting


def truthy_env(name: str) -> bool:
    v = os.environ.get(name, "").strip().lower()
    return v in ("1", "true", "yes", "on")


def build_text(row: dict) -> str:
    """Build rich text representation for a layanan row."""
    parts = [row["nama_pelayanan"]]

    syarat = row["syarat"]
    if isinstance(syarat, str):
        syarat = json.loads(syarat)

    wajib = syarat.get("wajib", [])
    kondisional = syarat.get("kondisional", [])

    if wajib:
        parts.append("Syarat wajib: " + "; ".join(wajib))
    if kondisional:
        parts.append("Syarat kondisional: " + "; ".join(kondisional))

    return ". ".join(parts)


def embed_text(client: genai.Client, text: str) -> list[float]:
    """Embed a single text string using Gemini."""
    result = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
    )
    return result.embeddings[0].values


def main():
    conn = psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        dbname=POSTGRES_DB,
    )
    cur = conn.cursor()

    if truthy_env("SEED_EMBEDDINGS_SKIP_IF_FULL"):
        cur.execute("SELECT COUNT(*) FROM layanan_konsuler")
        (total,) = cur.fetchone()
        cur.execute(
            "SELECT COUNT(*) FROM layanan_konsuler WHERE embedding IS NOT NULL"
        )
        (with_emb,) = cur.fetchone()
        if total > 0 and total == with_emb:
            cur.close()
            conn.close()
            print(
                f"SEED_EMBEDDINGS_SKIP_IF_FULL: all {total} rows already embedded — skipping API."
            )
            sys.exit(0)

    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not gemini_key:
        cur.close()
        conn.close()
        print("GEMINI_API_KEY is required unless SEED_EMBEDDINGS_SKIP_IF_FULL skips all work.", file=sys.stderr)
        sys.exit(1)

    client = genai.Client(api_key=gemini_key)

    cur.execute(
        "SELECT id, kode_pelayanan, nama_pelayanan, syarat FROM layanan_konsuler ORDER BY id"
    )
    rows = cur.fetchall()
    print(f"Found {len(rows)} rows to embed.")

    if not rows:
        cur.close()
        conn.close()
        print("No rows in layanan_konsuler — nothing to do.")
        sys.exit(0)

    success = 0
    for row_id, kode, nama, syarat in rows:
        row_dict = {"nama_pelayanan": nama, "syarat": syarat}
        text = build_text(row_dict)

        try:
            embedding = embed_text(client, text)
            vec_str = "[" + ",".join(str(v) for v in embedding) + "]"
            cur.execute(
                "UPDATE layanan_konsuler SET embedding = %s WHERE id = %s",
                (vec_str, row_id),
            )
            conn.commit()
            print(f"  [{kode}] {nama[:50]} — OK ({len(embedding)}d)")
            success += 1
        except Exception as e:
            conn.rollback()
            print(f"  [{kode}] ERROR: {e}")

        time.sleep(BATCH_DELAY)

    cur.close()
    conn.close()
    print(f"\nDone. {success}/{len(rows)} rows embedded.")

    if success != len(rows):
        sys.exit(1)


if __name__ == "__main__":
    main()
