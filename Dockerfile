FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY chatbot_kjri_dubai/ ./chatbot_kjri_dubai/

EXPOSE 8000

CMD ["adk", "web", "--host", "0.0.0.0", "--port", "8000"]
