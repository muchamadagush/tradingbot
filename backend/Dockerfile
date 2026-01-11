# File: backend/Dockerfile

# 1. Gunakan Python 3.12 agar sama persis dengan lokal
FROM python:3.12-slim

# 2. Set working directory
WORKDIR /app

# 3. Install system dependencies
# (build-essential sering dibutuhkan library crypto/solana untuk compile di Linux)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 4. Copy file requirements BARU yang tadi kita buat
COPY requirements_docker.txt .

# 5. Install dependencies dari file baru tersebut
RUN pip install --no-cache-dir -r requirements_docker.txt

# 6. Copy seluruh source code backend
COPY . .

# 7. Expose port FastAPI
EXPOSE 8000

# 8. Jalankan aplikasi
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]