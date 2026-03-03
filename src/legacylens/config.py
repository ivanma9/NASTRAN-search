from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    voyage_api_key: str = ""
    openai_api_key: str = ""
    chromadb_path: str = "data/chromadb"
    collection_name: str = "nastran95"
    embedding_model: str = "voyage-code-3"
    llm_model: str = "gpt-4o-mini"
    chunk_max_tokens: int = 1500
    top_k: int = 5

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


def get_settings() -> Settings:
    return Settings()
