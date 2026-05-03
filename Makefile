# KJRI Dubai Chatbot Makefile

.PHONY: help start stop restart status logs clean telegram-logs telegram-restart

# Default target
help:
	@echo "KJRI Dubai Chatbot Commands"
	@echo "==========================="
	@echo ""
	@echo "  make start         - Start all services"
	@echo "  make stop          - Stop all services"
	@echo "  make restart       - Restart all services"
	@echo "  make status        - Show container status and ngrok public URL"
	@echo "  make logs          - Stream logs from all containers"
	@echo "  make clean         - Stop and remove containers + volumes"
	@echo "  make telegram-logs - Stream Telegram bot logs"
	@echo "  make telegram-restart - Rebuild and restart Telegram bot"
	@echo ""
	@echo "Note: GEMINI_API_KEY harus ada di .env — layanan-embedding-seed mengisi pgvector untuk"
	@echo "       cari-layanan-semantik sebelum toolbox/agent/telegram-bot start."

start:
	@chmod +x start.sh && ./start.sh

stop:
	@echo "Stopping all services..."
	@docker compose down

restart:
	@echo "Restarting all services..."
	@docker compose down
	@docker compose up -d

status:
	@echo "Container Status:"
	@docker compose ps
	@echo ""
	@echo "Public URL (ngrok):"
	@curl -s http://localhost:4040/api/tunnels 2>/dev/null | grep -o '"public_url":"https://[^"]*' | head -1 | sed 's/"public_url":"//' || echo "Ngrok not available yet — try again in a few seconds"

logs:
	@docker compose logs -f

clean:
	@echo "Removing containers and volumes..."
	@docker compose down -v
	@echo "Cleanup complete."

telegram-logs:
	@docker compose logs -f telegram-bot

telegram-restart:
	@echo "Rebuilding and restarting Telegram bot..."
	@docker compose up -d --build telegram-bot
