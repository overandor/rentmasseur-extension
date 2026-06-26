FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser
RUN python -m playwright install chromium

COPY . .

ENV PYTHONUNBUFFERED=1
ENV PORT=7860

EXPOSE 7860

CMD ["python3", "-m", "uvicorn", "hf_app:app", "--host", "0.0.0.0", "--port", "7860"]
