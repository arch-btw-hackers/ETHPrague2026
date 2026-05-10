FROM python:3.12-slim

WORKDIR /app

# Build and install liboqs (required by the oqs Python package for Kyber768)
RUN apt-get update && apt-get install -y --no-install-recommends \
        cmake ninja-build libssl-dev git build-essential \
    && git clone --depth 1 --branch 0.10.1 https://github.com/open-quantum-safe/liboqs.git /tmp/liboqs \
    && cmake -S /tmp/liboqs -B /tmp/liboqs/build \
            -GNinja \
            -DBUILD_SHARED_LIBS=ON \
            -DOQS_MINIMAL_BUILD="KEM_kyber_768" \
            -DOQS_USE_OPENSSL=OFF \
            -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /tmp/liboqs/build \
    && cmake --install /tmp/liboqs/build \
    && echo '/usr/local/lib' > /etc/ld.so.conf.d/liboqs.conf \
    && ldconfig \
    && rm -rf /tmp/liboqs \
    && apt-get purge -y cmake ninja-build git build-essential \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Make sure the linker can find liboqs at runtime
ENV LD_LIBRARY_PATH=/usr/local/lib

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pre-create /data so the RSA key can be written there on first boot even if
# the Docker volume isn't mounted (e.g. in CI).  When the named volume IS
# mounted the directory is overlaid but the permissions are inherited.
RUN mkdir -p /data && chmod 777 /data

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
