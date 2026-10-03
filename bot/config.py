from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    telegram_bot_token: str
    backend_api_base_url: str = "http://api:8000"
    bot_db_path: str = "/code/bot_data/bot.sqlite3"


settings = BotSettings()