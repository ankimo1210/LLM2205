from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    vllm_base_url: str = "http://vllm:8001"
    vllm_model_id: str = "Qwen/Qwen2.5-7B-Instruct"
    system_prompt: str = "You are a helpful assistant. Answer concisely and accurately."
    system_prompt_file: str = ""
    database_url: str = "sqlite:////data/chat.db"

    def get_system_prompt(self) -> str:
        """Return system prompt from file if available, else from env."""
        if self.system_prompt_file:
            p = Path(self.system_prompt_file)
            if p.is_file():
                return p.read_text(encoding="utf-8").strip()
        return self.system_prompt


settings = Settings()
