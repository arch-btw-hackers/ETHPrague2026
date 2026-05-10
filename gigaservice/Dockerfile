FROM python:3.12-slim

# Добавил pkg-config на всякий случай, убрал libssl-dev за ненадобностью
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    ninja-build \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt
# Отключаем OpenSSL (-DOQS_USE_OPENSSL=OFF), чтобы CMake не искал системные либы
# Включаем DIST_BUILD, чтобы код точно запустился на процессоре сервера без ошибок совместимости
RUN git clone --depth 1 --branch 0.8.0 https://github.com/open-quantum-safe/liboqs.git \
    && cd liboqs \
    && mkdir build && cd build \
    && cmake -GNinja -DBUILD_SHARED_LIBS=ON -DOQS_USE_OPENSSL=OFF -DOQS_DIST_BUILD=ON .. \
    && ninja install

ENV LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]