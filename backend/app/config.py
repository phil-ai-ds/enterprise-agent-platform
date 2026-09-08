from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EAP_", env_file=".env", extra="ignore")

    app_name: str = "Enterprise Agent Platform"
    database_url: str = "sqlite:///./eap.db"
    secret_key: str = "dev-secret-change-me-9f1c2e8a4b7d6f0e3a5c8b1d4e7f0a2c"
    token_ttl_minutes: int = 60 * 12
    data_dir: str = "./data"
    default_deepseek_key: str = "sk-9e68b745b5de45e198470208c2fdeff0"
    default_deepseek_base: str = "https://api.deepseek.com"
    default_deepseek_model: str = "deepseek-v4-flash"
    frontend_dir: str = "frontend"


settings = Settings()
