from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import Optional

class Settings(BaseSettings):
    app_env: str = Field(default="production", env="APP_ENV")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    
    # vLLM Settings
    vllm_host: str = Field(default="vllm-engine", env="VLLM_HOST")
    vllm_port: int = Field(default=8000, env="VLLM_PORT")
    vllm_model_name: str = Field(default="Qwen/Qwen2.5-7B-Instruct-AWQ", env="VLLM_MODEL_NAME")
    
    # Qdrant Settings
    qdrant_host: str = Field(default="qdrant-vector-db", env="QDRANT_HOST")
    qdrant_port: int = Field(default=6333, env="QDRANT_PORT")
    
    # Redis Settings
    redis_host: str = Field(default="redis-cache", env="REDIS_HOST")
    redis_port: int = Field(default=6379, env="REDIS_PORT")
    redis_cache_ttl: int = Field(default=86400, env="REDIS_CACHE_TTL")
    semantic_cache_threshold: float = Field(default=0.92, env="SEMANTIC_CACHE_THRESHOLD")
    demo_mode: bool = Field(default=False, env="DEMO_MODE")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore")

    @property
    def vllm_base_url(self) -> str:
        return f"http://{self.vllm_host}:{self.vllm_port}/v1"

    @property
    def qdrant_url(self) -> str:
        return f"http://{self.qdrant_host}:{self.qdrant_port}"
        
    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    @field_validator("semantic_cache_threshold")
    @classmethod
    def check_threshold(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("semantic_cache_threshold must be between 0.0 and 1.0")
        return v

settings = Settings()
