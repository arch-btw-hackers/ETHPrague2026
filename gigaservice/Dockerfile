FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pre-create /data so the RSA key can be written there on first boot even if
# the Docker volume isn't mounted (e.g. in CI).  When the named volume IS
# mounted the directory is overlaid but the permissions are inherited.
RUN mkdir -p /data && chmod 777 /data

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
