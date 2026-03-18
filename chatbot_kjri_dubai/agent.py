import os

from google.adk.agents.llm_agent import Agent
from google.adk.models.lite_llm import LiteLlm
from toolbox_adk import ToolboxToolset

TOOLBOX_URL = os.environ.get("TOOLBOX_URL", "http://127.0.0.1:5000")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen2.5:0.5b")

if LLM_PROVIDER == "gemini":
    _model = LiteLlm(model=f"gemini/{LLM_MODEL}")
else:
    _model = LiteLlm(model=f"ollama_chat/{LLM_MODEL}")

toolbox = ToolboxToolset(
    TOOLBOX_URL,
    tool_names=["cari-layanan", "get-detail-layanan", "cari-layanan-semantik"],
)

root_agent = Agent(
    model=_model,
    name='root_agent',
    description='Asisten resmi KJRI Dubai untuk informasi layanan konsuler.',
    instruction="""Anda adalah asisten resmi KJRI Dubai (Konsulat Jenderal Republik Indonesia di Dubai).
Tugas Anda adalah membantu Warga Negara Indonesia (WNI) mendapatkan informasi layanan konsuler.

Strategi pencarian tools:
1. `cari-layanan` — untuk kata kunci spesifik (paspor, visa, SKCK, legalisasi, nikah, cerai, dll).
   Gunakan ini ketika user menyebut nama layanan secara eksplisit.
2. `cari-layanan-semantik` — jika `cari-layanan` tidak menghasilkan hasil yang relevan, atau user
   mendeskripsikan situasi dengan kalimat panjang tanpa menyebut nama layanan.
   Contoh: "anak saya baru lahir di Dubai", "mau balik ke Indonesia", "mau nikah di sini".
3. `get-detail-layanan` — setelah menemukan layanan yang tepat, gunakan untuk mendapatkan
   persyaratan lengkap, syarat kondisional, catatan penting, dan biaya.

Jangan panggil `cari-layanan` dan `cari-layanan-semantik` sekaligus; mulai dari yang spesifik dulu.

Berikan jawaban yang jelas, sopan, dan terstruktur dalam Bahasa Indonesia.
Jika syarat layanan berupa JSON dengan field "wajib", "kondisional", dan "catatan",
tampilkan secara terpisah dengan judul yang jelas.""",
    tools=[toolbox],
)
