FROM python:3.11-slim

# Install CTF tool binaries
RUN apt-get update && apt-get install -y --no-install-recommends \
    nmap \
    libimage-exiftool-perl \
    binutils \
    file \
    binwalk \
    radare2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

RUN mkdir -p workspace reports

ENTRYPOINT ["python", "runner.py"]
