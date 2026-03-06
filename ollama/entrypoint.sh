#!/bin/sh
set -e

ollama serve &
sleep 10
ollama pull qwen3.5:0.8b
wait
