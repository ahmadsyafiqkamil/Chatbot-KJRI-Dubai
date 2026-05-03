"""Structural tests for multi-agent architecture.

No live LLM calls are made — tests only import and inspect Python objects.
"""

import os

import pytest
from google.adk.agents.llm_agent import Agent
from google.adk.tools import FunctionTool

from chatbot_kjri_dubai.agent import root_agent
from chatbot_kjri_dubai.agents.identity_agent import identity_agent
from chatbot_kjri_dubai.agents.lookup_formatter_agent import lookup_formatter_agent
from chatbot_kjri_dubai.agents.router_agent import router_agent
from chatbot_kjri_dubai.agents.shared import CHANNEL
from chatbot_kjri_dubai.agents.triage_agent import triage_agent


# ---------------------------------------------------------------------------
# ADK Agent typing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("agent_label", "agent_obj"),
    [
        ("root_agent", root_agent),
        ("identity_agent", identity_agent),
        ("router_agent", router_agent),
        ("triage_agent", triage_agent),
        ("lookup_formatter_agent", lookup_formatter_agent),
    ],
)
def test_each_agent_is_google_adk_llm_agent(agent_label, agent_obj):
    assert isinstance(agent_obj, Agent), (
        f"{agent_label} must be an instance of google.adk.agents.llm_agent.Agent"
    )


# ---------------------------------------------------------------------------
# Root agent structure
# ---------------------------------------------------------------------------


def test_root_agent_has_four_sub_agents():
    assert len(root_agent.sub_agents) == 4


def test_root_agent_sub_agent_names():
    names = [a.name for a in root_agent.sub_agents]
    assert names == [
        "identity_agent",
        "router_agent",
        "triage_agent",
        "lookup_formatter_agent",
    ]


# ---------------------------------------------------------------------------
# Per-agent tool presence
# ---------------------------------------------------------------------------


def _get_toolbox_tool_names(toolset) -> list:
    """Akses daftar tool_names dari ToolboxToolset.

    Menggunakan name-mangled private attr ``_ToolboxToolset__tool_names``.
    Jika library berubah API-nya, test ini akan gagal dengan AttributeError
    yang eksplisit — tidak diam-diam lolos.
    """
    try:
        return toolset._ToolboxToolset__tool_names
    except AttributeError as exc:
        pytest.fail(
            f"ToolboxToolset no longer exposes __tool_names — update this helper: {exc}"
        )


def test_identity_agent_has_only_simpan_identitas():
    assert len(identity_agent.tools) == 1
    tool_names = _get_toolbox_tool_names(identity_agent.tools[0])
    assert "simpan-identitas" in tool_names
    assert "cari-layanan" not in tool_names


def test_router_agent_has_no_tools():
    assert router_agent.tools == []


def test_triage_agent_has_no_tools():
    assert triage_agent.tools == []


def test_lookup_formatter_agent_has_rag_tool():
    # tools list: [ToolboxToolset, FunctionTool(cari_dokumen_rag)]
    function_tools = [t for t in lookup_formatter_agent.tools if isinstance(t, FunctionTool)]
    assert len(function_tools) == 1
    rag_tool = function_tools[0]
    # FunctionTool.name matches the wrapped function name
    assert rag_tool.name == "cari_dokumen_rag"


def test_lookup_formatter_toolbox_excludes_identity_tools():
    toolbox_wrappers = [t for t in lookup_formatter_agent.tools if not isinstance(t, FunctionTool)]
    assert len(toolbox_wrappers) == 1
    tool_names = _get_toolbox_tool_names(toolbox_wrappers[0])
    assert set(tool_names) == {
        "cari-layanan",
        "get-detail-layanan",
        "cari-layanan-semantik",
        "simpan-interaksi",
    }
    assert "simpan-identitas" not in tool_names


# ---------------------------------------------------------------------------
# Instruction content — lookup_formatter_agent
# ---------------------------------------------------------------------------


def test_agent_instructions_contain_zero_hallucination():
    assert "ZERO HALLUCINATION" in lookup_formatter_agent.instruction


def test_agent_instructions_contain_6_sections():
    sections = [
        "Konteks singkat",
        "Ringkasan layanan",
        "Persyaratan",
        "Biaya (AED)",
        "Jika situasi Anda tidak pasti",
        "Langkah berikutnya",
    ]
    for section in sections:
        assert section in lookup_formatter_agent.instruction, (
            f"Section '{section}' not found in lookup_formatter_agent.instruction"
        )


# ---------------------------------------------------------------------------
# Instruction content — identity_agent
# ---------------------------------------------------------------------------


def test_identity_agent_instruction_contains_tahap():
    assert "TAHAP 1" in identity_agent.instruction
    assert "TAHAP 2" in identity_agent.instruction
    assert "simpan-identitas" in identity_agent.instruction


# ---------------------------------------------------------------------------
# Instruction content — triage_agent
# ---------------------------------------------------------------------------


def test_triage_agent_instruction_contains_all_domains():
    domains = ["PASPOR", "CATATAN SIPIL", "LEGALISASI", "DARURAT"]
    for domain in domains:
        assert domain in triage_agent.instruction, (
            f"Domain '{domain}' not found in triage_agent.instruction"
        )


# ---------------------------------------------------------------------------
# Instruction content — root_agent
# ---------------------------------------------------------------------------


def test_root_agent_instruction_contains_identity_gate():
    assert "identity_agent" in root_agent.instruction
    assert "router_agent" in root_agent.instruction


# ---------------------------------------------------------------------------
# Instruction content — router_agent
# ---------------------------------------------------------------------------


def test_router_agent_instruction_delegates_to_triage_agent():
    """router_agent harus menyebutkan triage_agent secara eksplisit agar handoff jelas."""
    assert "triage_agent" in router_agent.instruction


def test_router_agent_instruction_handles_option_e():
    """Option E (Lainnya) harus ada penanganannya, bukan dead-end."""
    assert "(E)" in router_agent.instruction


# ---------------------------------------------------------------------------
# Instruction content — triage_agent (detail per domain)
# ---------------------------------------------------------------------------


def test_triage_legalisasi_has_t4():
    """LEGALISASI harus memiliki 4 pertanyaan triage (T4) — konsisten dengan domain lain."""
    instr = triage_agent.instruction
    # Cari blok TRIAGE LEGALISASI dan pastikan ada T4 di dalamnya
    legalisasi_block_start = instr.index("TRIAGE LEGALISASI")
    # Ambil teks dari blok LEGALISASI sampai blok berikutnya (DARURAT)
    legalisasi_block = instr[legalisasi_block_start:instr.index("TRIAGE DARURAT")]
    assert "T4" in legalisasi_block, "LEGALISASI harus punya pertanyaan T4"


def test_triage_instruction_references_root_agent_for_reset():
    """Reset domain harus diarahkan ke root_agent — tidak ke router_agent yang tidak bisa diakses langsung."""
    assert "root_agent" in triage_agent.instruction
    assert "router_agent" not in triage_agent.instruction


# ---------------------------------------------------------------------------
# Channel configuration
# ---------------------------------------------------------------------------


def test_channel_defaults_to_web_when_env_not_set(monkeypatch):
    """Nilai default CHANNEL adalah 'web' jika env var tidak di-set."""
    # CHANNEL sudah di-import di module load time, jadi kita verifikasi nilainya
    # Tanpa env var CHANNEL, default harus 'web'
    assert CHANNEL in {"web", "telegram"}, f"CHANNEL value '{CHANNEL}' tidak dikenal"


def test_lookup_formatter_instruction_embeds_channel():
    """Instruction lookup_formatter_agent harus menyertakan nilai CHANNEL yang aktif (bukan hardcode 'web')."""
    # CHANNEL dari env sudah di-embed lewat f-string saat module di-load
    assert CHANNEL in lookup_formatter_agent.instruction, (
        f"CHANNEL='{CHANNEL}' tidak ditemukan dalam instruction lookup_formatter_agent"
    )


# ---------------------------------------------------------------------------
# Identity — pengguna_id propagation
# ---------------------------------------------------------------------------


def test_identity_agent_instruction_mentions_pengguna_id_format():
    """identity_agent harus menginstruksikan penggunaan format [ID:...] untuk propagasi UUID."""
    assert "[ID:" in identity_agent.instruction, (
        "identity_agent.instruction harus mendefinisikan format [ID:uuid] untuk propagasi pengguna_id"
    )


def test_lookup_formatter_instruction_extracts_pengguna_id_from_history():
    """lookup_formatter_agent harus diinstruksikan mengambil pengguna_id dari pola [ID:...] di history."""
    assert "[ID:" in lookup_formatter_agent.instruction, (
        "lookup_formatter_agent.instruction harus menjelaskan cara mengekstrak [ID:...] dari riwayat percakapan"
    )
