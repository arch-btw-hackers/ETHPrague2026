# ── Stage 1: build liboqs ──────────────────────────────────────────────────
FROM python:3.12-slim AS liboqs-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        cmake ninja-build git build-essential \
    && git clone --depth 1 --branch 0.10.1 \
        https://github.com/open-quantum-safe/liboqs.git /tmp/liboqs \
    && cmake -S /tmp/liboqs -B /tmp/liboqs/build \
            -GNinja \
            -DBUILD_SHARED_LIBS=ON \
            -DOQS_MINIMAL_BUILD="KEM_kyber_768" \
            -DOQS_USE_OPENSSL=OFF \
            -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /tmp/liboqs/build \
    && cmake --install /tmp/liboqs/build

# ── Stage 2: runtime ───────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Copy only the compiled .so from the builder — no build tools in final image
COPY --from=liboqs-builder /usr/local/lib/liboqs.so* /usr/local/lib/
RUN ldconfig

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pre-create /data so the RSA key can be written there on first boot even if
# the Docker volume isn't mounted (e.g. in CI).  When the named volume IS
# mounted the directory is overlaid but the permissions are inherited.
RUN mkdir -p /data && chmod 777 /data

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
