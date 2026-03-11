# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A consular services chatbot for KJRI Dubai (Indonesian Consulate General in Dubai) that helps Indonesian citizens find information about available services, requirements, and costs. Built with Google ADK (Agent Development Kit), it responds in Bahasa Indonesia.

## Development Commands

### Setup
```bash
# Full server setup (Debian/Ubuntu)
chmod +x install.sh && ./install.sh

# Manual setup
cp .env.example .env
# Edit .env with your values, then:
docker compose up -d
```

### Running the Agent
```bash
# Start all services (PostgreSQL, Toolbox, pgAdmin, Agent)
docker compose up -d

# Run agent locally for development (requires LiteLLM/Ollama running)
adk web --host 0.0.0.0 --port 8000

# View logs
docker compose logs -f agent
docker compose logs -f toolbox
```

### Service URLs
- Agent API/UI: `http://localhost:8000`
- pgAdmin: `http://localhost:5050`
- Ollama: `http://localhost:11434`

## Architecture

### Stack
- **Framework**: Google ADK v1.26.0 (`google-adk`)
- **LLM routing**: LiteLLM v1.82.0 (abstracts Ollama/Gemini)
- **Database tools**: `toolbox-adk` + `toolbox-core` v0.5.8 (MCP Toolbox)
- **Database**: PostgreSQL 16, initialized from `rag_kjri_dubai.sql` (gitignored)
- **Containers**: Docker Compose with 4 services: `postgres`, `toolbox`, `pgadmin`, `agent`

### How It Works

```
User → ADK Agent (port 8000)
          ↓ tool calls
       MCP Toolbox (port 5001) → PostgreSQL (port 5432)
          ↓ LLM calls
       Ollama (local) OR Google Gemini (cloud)
```

The agent in [chatbot_kjri_dubai/agent.py](chatbot_kjri_dubai/agent.py) is the only source of agent logic. It:
1. Loads LLM config from environment (`LLM_PROVIDER`, `LLM_MODEL`)
2. Connects to MCP Toolbox at `TOOLBOX_URL` to get two SQL-backed tools
3. Runs as a `google.adk.Agent` with an Indonesian-language system prompt

### Available Tools (via MCP Toolbox)
Defined in [toolbox/config/tools.yaml](toolbox/config/tools.yaml):
- `cari-layanan` — keyword search over consular services (returns code, name, cost in AED)
- `get-detail-layanan` — full detail for a service (requirements, costs, notes) by code or name

### LLM Configuration
Set in `.env`:
```
LLM_PROVIDER=ollama        # or "gemini"
LLM_MODEL=qwen2.5:0.5b    # any Ollama model, or gemini model name
GEMINI_API_KEY=            # required if LLM_PROVIDER=gemini
OLLAMA_API_BASE=http://localhost:11434
```

LiteLLM model string is constructed as `ollama_chat/<model>` for Ollama or `gemini/<model>` for Gemini.

### Database
The PostgreSQL schema and data live in `rag_kjri_dubai.sql` (gitignored — do not commit). The `toolbox` service mounts this file and runs it on first start. To add/modify services, edit the SQL file and reinitialize the database.

### Adding New Tools
1. Add a new SQL query tool in [toolbox/config/tools.yaml](toolbox/config/tools.yaml)
2. Register it in the `tools` list inside [chatbot_kjri_dubai/agent.py](chatbot_kjri_dubai/agent.py) by adding it to the `toolbox.load_toolset()` call or individual tool loads
3. Update the agent's instruction prompt if the tool changes response behavior
