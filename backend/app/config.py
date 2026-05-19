from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://rental:rental@rental-db:5432/rental"
    # JWT signing key — fail fast if empty. Generate with: openssl rand -hex 32
    secret_key: str = ""
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 8  # 8 hours
    upload_dir: str = "/app/uploads"
    default_admin_username: str = "admin"
    default_admin_password: str = "admin123"
    # AES-256-GCM key for landlord signature encryption. 32 raw bytes encoded
    # as 64 hex chars. Generate with: openssl rand -hex 32. Required.
    signature_encryption_key: str = ""
    # Toggle the Secure flag on the session cookie. Set to true when the app
    # is served over HTTPS.
    cookie_secure: bool = False
    # Per-IP rate limit on /api/auth/login. Format accepted by slowapi.
    login_rate_limit: str = "5/minute"

    class Config:
        env_file = ".env"


settings = Settings()

if not settings.secret_key:
    raise RuntimeError(
        "SECRET_KEY is required. Generate one with: openssl rand -hex 32"
    )
