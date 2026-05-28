from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    openai_stt_model: str = "whisper-1"
    openai_extract_model: str = "gpt-4o"
    openai_diarize_model: str = "gpt-4o-mini"

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "talkgraph-dev"

    data_dir: str = "./data"


@lru_cache
def get_settings() -> Settings:
    return Settings()
