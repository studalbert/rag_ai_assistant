from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    upload_dir: str = "/code/uploads"
    max_upload_size_mb: int = 20

    chunk_size: int = 1000       # в символах — простое приближение;
                                  # точнее было бы считать в токенах, но для MVP этого достаточно
    chunk_overlap: int = 200

    # Лимиты "бесплатного тарифа" — бизнес-логика, а не защита от спама
    # (за защиту от спама отвечает rate_limit.py). Можно переопределить через .env
    daily_question_limit: int = 20
    max_documents_per_user: int = 20

    # Название модели на HuggingFace Hub — sentence-transformers скачает её
    # автоматически при первом использовании и закэширует локально
    embedding_model: str = "intfloat/multilingual-e5-base"

    yandex_api_key: str
    yandex_folder_id: str
    # yandexgpt-lite — быстрее и дешевле; yandexgpt — качественнее, если понадобится
    yandex_gpt_model: str = "yandexgpt-lite"


settings = Settings()