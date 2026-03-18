#!/bin/bash

# Start KJRI Dubai Chatbot with ngrok URL auto-detection

set -e

echo "KJRI Dubai Chatbot - Starting..."
echo "================================"
echo ""

# --- Ensure .env exists ---
if [ ! -f .env ]; then
    echo "Creating .env from template..."
    cp .env.example .env
fi

# --- Check / update NGROK_AUTHTOKEN ---
# Priority: shell env var > .env file > prompt
ENV_TOKEN=$(grep "^NGROK_AUTHTOKEN=" .env | cut -d'=' -f2)

if [ -n "$NGROK_AUTHTOKEN" ] && [ "$NGROK_AUTHTOKEN" != "$ENV_TOKEN" ]; then
    # Shell env var is set and differs from .env — update .env silently
    if grep -q "^NGROK_AUTHTOKEN=" .env; then
        awk -v token="$NGROK_AUTHTOKEN" '/^NGROK_AUTHTOKEN=/ { print "NGROK_AUTHTOKEN=" token; next } { print }' .env > .env.tmp && mv .env.tmp .env
    else
        echo "NGROK_AUTHTOKEN=$NGROK_AUTHTOKEN" >> .env
    fi
    echo "NGROK_AUTHTOKEN updated in .env"
elif [ -z "$ENV_TOKEN" ] && [ -z "$NGROK_AUTHTOKEN" ]; then
    # Neither env var nor .env has the token — prompt once and save
    echo "NGROK_AUTHTOKEN belum diset."
    echo -n "Masukkan ngrok authtoken: "
    read -r NGROK_AUTHTOKEN
    if [ -z "$NGROK_AUTHTOKEN" ]; then
        echo "Error: NGROK_AUTHTOKEN wajib diisi."
        exit 1
    fi
    if grep -q "^NGROK_AUTHTOKEN=" .env; then
        awk -v token="$NGROK_AUTHTOKEN" '/^NGROK_AUTHTOKEN=/ { print "NGROK_AUTHTOKEN=" token; next } { print }' .env > .env.tmp && mv .env.tmp .env
    else
        echo "NGROK_AUTHTOKEN=$NGROK_AUTHTOKEN" >> .env
    fi
    echo "NGROK_AUTHTOKEN disimpan ke .env — tidak akan ditanya lagi."
    echo ""
fi

# --- Start all services ---
echo "Starting all services..."
docker compose up -d
echo ""

# --- Wait for ngrok public URL ---
echo "Waiting for ngrok tunnel..."
MAX_ATTEMPTS=30
ATTEMPT=1

while [ $ATTEMPT -le $MAX_ATTEMPTS ]; do
    PUBLIC_URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null \
        | grep -o '"public_url":"https://[^"]*' | head -1 | cut -d'"' -f4)

    if [ -n "$PUBLIC_URL" ]; then
        break
    fi

    echo "  Attempt $ATTEMPT/$MAX_ATTEMPTS - waiting..."
    sleep 3
    ((ATTEMPT++))
done

echo ""
if [ -z "$PUBLIC_URL" ]; then
    echo "Warning: Could not get ngrok URL. Check: docker compose logs ngrok"
else
    echo "========================================"
    echo "  Public URL : $PUBLIC_URL"
    echo "  Local URL  : http://localhost:8000"
    echo "  Ngrok dash : http://localhost:4040"
    echo "========================================"
fi
