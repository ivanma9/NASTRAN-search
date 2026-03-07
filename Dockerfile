FROM python:3.11-slim

WORKDIR /app

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files
COPY pyproject.toml uv.lock* ./
COPY src/ src/

# Install dependencies
RUN uv pip install --system .

# Copy pre-built data (ChromaDB + indices)
COPY data/ data/

# Expose port
EXPOSE 8000

# Run the FastAPI server
CMD ["sh", "-c", "uvicorn legacylens.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
