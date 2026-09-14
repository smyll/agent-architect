"""Model configuration shared by the smoke check and future application."""
import os
from pathlib import Path

from dotenv import load_dotenv
from strands.models.openai import OpenAIModel


def create_model(*, max_tokens=1000, settings=None):
    load_dotenv(Path(__file__).parent / ".env")
    settings = settings or {}
    provider = settings.get("provider") or os.getenv("MODEL_PROVIDER", "deepseek")
    if provider not in {"deepseek", "openai_compatible"}:
        raise ValueError("Unsupported provider")
    key_name = "DEEPSEEK_API_KEY" if provider == "deepseek" else "MODEL_API_KEY"
    key = settings.get("api_key") or os.getenv(key_name)
    if not key:
        raise ValueError("Missing model credentials")
    model_id = settings.get("model_id") or os.getenv("MODEL_ID") or ("deepseek-flash" if provider == "deepseek" else "")
    base_url = settings.get("base_url") or os.getenv("MODEL_BASE_URL") or ("https://api.deepseek.com" if provider == "deepseek" else "")
    if not model_id or not base_url:
        raise ValueError("Missing model configuration")
    params = {"max_tokens": max_tokens, "temperature": 0}
    if provider == "deepseek":
        params["extra_body"] = {"thinking": {"type": "disabled"}}
    return OpenAIModel(
        client_args={"api_key": key, "base_url": base_url, "timeout": 45.0, "max_retries": 0},
        model_id=model_id,
        params=params,
    )
