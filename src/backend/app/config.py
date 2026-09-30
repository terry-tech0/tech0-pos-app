"""環境変数の読み込み。設計仕様書 §2.4 環境変数。

秘密情報はコードに書かず、すべて環境変数で渡す（NFR-SEC-03）。
JWT_SECRET_KEY と DATABASE_URL は既定値を持たせない。
未設定なら起動時に落とす（IT-003 が「環境変数未設定時に起動失敗」を確認する）。
"""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


class ConfigError(RuntimeError):
    """必須の環境変数が無いまま起動しようとしたときに投げる。"""


def _required(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise ConfigError(
            f"環境変数 {key} が設定されていません。"
            f".env（ローカル）または App Service のアプリケーション設定を確認してください。"
        )
    return value


class Settings:
    """アプリ全体の設定。"""

    def __init__(self) -> None:
        # DB。SSL必須（設計 §2.2 FastAPI⇄MySQL の境界）
        self.database_url: str = _required("DATABASE_URL")

        # Azure Database for MySQL は SSL 必須。ローカルMySQLでは false にする
        self.db_ssl: bool = os.getenv("DB_SSL", "true").lower() == "true"

        # JWT。設計 §8.2
        self.jwt_secret_key: str = _required("JWT_SECRET_KEY")
        self.jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
        self.jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))
        self.jwt_issuer: str = os.getenv("JWT_ISSUER", "tech0-pos-app")

        # local / production。production では Swagger を無効化（設計 §8.7）
        self.app_env: str = os.getenv("APP_ENV", "local")

        # 既定は空＝誰も許可しない（設計 §8.5）
        self.cors_allowed_origins: list[str] = [
            origin.strip()
            for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
            if origin.strip()
        ]

        # ログイン連続失敗の制限。設計 §8.1 S-4
        self.login_max_attempts: int = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
        self.login_lockout_seconds: int = int(os.getenv("LOGIN_LOCKOUT_SECONDS", "60"))

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """設定を1度だけ読む。"""
    return Settings()
