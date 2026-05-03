from __future__ import annotations

import json
import logging
import os
import threading
from typing import TYPE_CHECKING

from google.adk.models import Gemini
from toolbox_adk import ToolboxToolset

if TYPE_CHECKING:
    from chatbot_kjri_dubai.rag.retrieval import Retriever

_logger = logging.getLogger(__name__)

TOOLBOX_URL = os.environ.get("TOOLBOX_URL", "http://127.0.0.1:5000")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen2.5:0.5b")

# Set env var CHANNEL=telegram untuk deployment Telegram; default "web" untuk ADK web UI.
CHANNEL = os.environ.get("CHANNEL", "web")

if LLM_PROVIDER == "gemini":
    _model = Gemini(model=LLM_MODEL)
else:
    from google.adk.models.lite_llm import LiteLlm
    _model = LiteLlm(model=f"ollama_chat/{LLM_MODEL}")

# Scoped per-agent toolboxes
identity_toolbox = ToolboxToolset(TOOLBOX_URL, tool_names=["simpan-identitas"])
lookup_toolbox = ToolboxToolset(
    TOOLBOX_URL,
    tool_names=[
        "cari-layanan",
        "get-detail-layanan",
        "cari-layanan-semantik",
        "simpan-interaksi",
    ],
)

_rag_retriever: "Retriever | None" = None
_rag_lock = threading.Lock()


def _get_retriever() -> "Retriever":
    """Lazy singleton dengan double-checked locking — aman untuk async/concurrent sessions."""
    global _rag_retriever
    if _rag_retriever is None:
        with _rag_lock:
            if _rag_retriever is None:
                from chatbot_kjri_dubai.rag.retrieval import retriever_from_env
                _rag_retriever = retriever_from_env()
    return _rag_retriever


def cari_dokumen_rag(
    pertanyaan: str,
    jumlah_maksimal: int = 5,
    alpha_kata_kunci: float = 0.4,
) -> str:
    """Cari cuplikan dari dokumen yang diunggah (PDF/MD/TXT) via hybrid retrieval (BM25 + vektor).

    Gunakan jika user menanyakan isi panduan, FAQ, atau materi kebijakan dari basis dokumen
    RAG — bukan untuk menggantikan daftar layanan konsuler di database layanan.

    Untuk biaya (AED) dan persyaratan resmi layanan konsuler tetap wajib memakai
    cari-layanan / get-detail-layanan. Jangan mengarang angka dari cuplikan dokumen saja.

    Args:
        pertanyaan (str): Pertanyaan atau kata kunci pencarian.
        jumlah_maksimal (int): Jumlah cuplikan maksimal (1–15, default 5).
        alpha_kata_kunci (float): Bobot pencarian kata kunci vs semantik, 0.0–1.0 (default 0.4).
    """
    try:
        r = _get_retriever()
        top_k = max(1, min(int(jumlah_maksimal), 15))
        alpha = max(0.0, min(float(alpha_kata_kunci), 1.0))
        rows = r.hybrid_retrieve(pertanyaan.strip(), top_k=top_k, alpha=alpha)
        return json.dumps({"sukses": True, "hasil": rows}, ensure_ascii=False)
    except Exception as e:
        _logger.error("cari_dokumen_rag failed: %s", e, exc_info=True)
        return json.dumps({"sukses": False, "error": str(e)}, ensure_ascii=False)
