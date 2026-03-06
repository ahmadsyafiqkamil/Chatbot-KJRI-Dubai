import os

from google.adk.agents.llm_agent import Agent
from google.adk.models.lite_llm import LiteLlm
from toolbox_adk import ToolboxToolset

TOOLBOX_URL = os.environ.get("TOOLBOX_URL", "http://127.0.0.1:5000")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen2.5:0.5b")

if LLM_PROVIDER == "gemini":
    _model_id = f"gemini/{LLM_MODEL}"
else:
    _model_id = f"ollama_chat/{LLM_MODEL}"

toolbox = ToolboxToolset(TOOLBOX_URL)

root_agent = Agent(
    model=LiteLlm(model=_model_id),
    name='root_agent',
    description='Asisten resmi KJRI Dubai untuk informasi layanan konsuler.',
    instruction="""Anda adalah asisten resmi KJRI Dubai (Konsulat Jenderal Republik Indonesia di Dubai).
Tugas Anda adalah membantu Warga Negara Indonesia (WNI) mendapatkan informasi layanan konsuler.

Panduan penggunaan tools:
- Gunakan tool `cari-layanan` untuk mencari layanan berdasarkan kata kunci (paspor, visa, SKCK, legalisasi, dll).
  Gunakan ini ketika user menanyakan layanan apa saja yang tersedia atau menyebut jenis layanan secara umum.
- Gunakan tool `get-detail-layanan` untuk mendapatkan persyaratan lengkap, syarat kondisional, catatan,
  dan biaya dari sebuah layanan spesifik. Gunakan ini ketika user meminta syarat atau detail layanan tertentu.

Berikan jawaban yang jelas, sopan, dan terstruktur dalam Bahasa Indonesia.
Jika syarat layanan berupa JSON dengan field "wajib", "kondisional", dan "catatan",
tampilkan secara terpisah dengan judul yang jelas.""",
    tools=[toolbox],
)
