FROM python:3.11-slim

WORKDIR /app

# Install uv and curl
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml uv.lock* ./
COPY src/ src/

# Install dependencies
RUN uv pip install --system .

# Download pre-built ChromaDB index from GitHub release
RUN curl -L https://github.com/ivanma9/NASTRAN-search/releases/download/v1.0-data/legacylens-data.tar.gz \
    | tar -xz

# Expose port
EXPOSE 8000

# Run the FastAPI server
CMD ["sh", "-c", "uvicorn legacylens.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
