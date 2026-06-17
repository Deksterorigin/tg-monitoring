import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    BOT_TOKEN: str
    FIRST_ADMIN_ID: int
    RENDER_EXTERNAL_URL: str = ""
    PORT: int = 8080
    DATABASE_PATH: str = "bot_database.db"

    
    # Для управления парсингом (значения по умолчанию)
    DEFAULT_MAX_PRICE_USD: float = 10.0
    DEFAULT_KEYWORDS: str = "ChatGPT,Claude,Perplexity,Midjourney"
    DEFAULT_PARSE_INTERVAL_MINUTES: int = 60

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
