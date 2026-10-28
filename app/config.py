import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    futu_host: str = os.getenv("FUTU_HOST", "127.0.0.1")
    futu_port: int = int(os.getenv("FUTU_PORT", "11111"))
    market: str = os.getenv("MARKET", "US").upper()
    demo_mode: bool = os.getenv("DEMO_MODE", "false").lower() in {"1", "true", "yes"}
    cache_seconds: int = int(os.getenv("CACHE_SECONDS", "60"))


settings = Settings()
