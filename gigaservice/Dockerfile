FROM python:3.12-slim

# 1. Ставим инструменты для автосборки C-кода (из Quickstart OQS)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    ninja-build \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Копируем зависимости
COPY requirements.txt .

# 3. КРИТИЧНО: Вырезаем возможные кривые пакеты oqs из requirements.txt, 
# чтобы pip не подтянул старый хлам из PyPI, а поставил только FastAPI, web3 и т.д.
RUN sed -i '/^oqs/d' requirements.txt && \
    sed -i '/^liboqs-python/d' requirements.txt && \
    pip install --no-cache-dir -r requirements.txt

# 4. Устанавливаем официальный враппер напрямую из GitHub
RUN git clone --depth 1 https://github.com/open-quantum-safe/liboqs-python.git \
    && cd liboqs-python \
    && pip install --no-cache-dir . \
    && cd .. \
    && rm -rf liboqs-python

# 5. МАГИЯ АВТОСБОРКИ
# Делаем один "холостой" импорт. В этот момент питон не найдет библиотеку, 
# сам скачает C-код liboqs, соберет его через CMake и положит куда надо.
RUN python -c "import oqs; print('Kyber (liboqs) successfully auto-compiled and loaded!')"

# 6. Копируем код твоего сервиса
COPY . .

RUN mkdir -p /data && chmod 777 /data
EXPOSE 8000
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]