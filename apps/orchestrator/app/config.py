from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    vllm_base_url: str = "http://vllm:8001"
    vllm_model_id: str = "Qwen/Qwen2.5-7B-Instruct"
    system_prompt: str = "You are a helpful assistant. Answer concisely and accurately."
    database_url: str = "sqlite:////data/chat.db"


settings = Settings()
