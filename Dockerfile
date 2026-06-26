FROM python:3.11-slim

# Install system dependencies including C++ compiler
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    build-essential \
    g++ \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser
RUN python -m playwright install chromium

COPY . .

# Compile C++ native OS server and engines
RUN g++ -O3 -std=c++17 -pthread cpp_os_server.cpp -o cpp_os_server && \
    g++ -O3 -std=c++17 -pthread rotator_engine.cpp -o rotator_engine && \
    g++ -O3 -std=c++17 -pthread ga_rl_optimizer.cpp -o ga_rl_optimizer

ENV PYTHONUNBUFFERED=1
ENV PORT=7860

EXPOSE 7860

CMD ["./cpp_os_server", "7860"]
