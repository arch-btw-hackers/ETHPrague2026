FROM python:3.12-slim

# Устанавливаем зависимости для сборки
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    ninja-build \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Клонируем и собираем liboqs (Open Quantum Safe)
WORKDIR /opt
RUN git clone --depth 1 --branch 0.8.0 https://github.com/open-quantum-safe/liboqs.git \
    && cd liboqs \
    && mkdir build && cd build \
    && cmake -GNinja -DBUILD_SHARED_LIBS=ON -DOQS_USE_OPENSSL=ON .. \
    && ninja install

# Настраиваем пути для библиотек
ENV LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/lib

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]