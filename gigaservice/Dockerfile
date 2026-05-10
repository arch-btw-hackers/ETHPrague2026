FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        software-properties-common \
    && add-apt-repository universe \
    && apt-get update && apt-get install -y --no-install-recommends \
        python3.12 python3-pip liboqs-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY . .
RUN mkdir -p /data && chmod 777 /data

EXPOSE 8000
CMD ["python3.12", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
