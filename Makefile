# KJRI Dubai Chatbot Makefile

.PHONY: help start stop restart status logs clean

# Default target
help:
	@echo "KJRI Dubai Chatbot Commands"
	@echo "==========================="
	@echo ""
	@echo "  make start    - Start all services (postgres, toolbox, pgadmin, chromadb, agent, ngrok)"
	@echo "  make stop     - Stop all services"
	@echo "  make restart  - Restart all services"
	@echo "  make status   - Show container status and ngrok public URL"
	@echo "  make logs     - Stream logs from all containers"
	@echo "  make clean    - Stop and remove containers + volumes"
	@echo ""

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
