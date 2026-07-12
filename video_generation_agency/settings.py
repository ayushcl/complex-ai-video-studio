"""Shared configuration for the Agency Swarm agents."""

import os

from dotenv import load_dotenv

DEFAULT_AGENCY_MODEL = "gemini-2.5-flash"
GEMINI_API_KEY_PLACEHOLDERS = {
    "your-gemini-api-key",
    "your-gemini-api-key-here",
}
LITELLM_PREFIX = "litellm/"
GEMINI_PROVIDER_PREFIX = "gemini/"


load_dotenv()


def configure_gemini_environment() -> None:
    """Make the Gemini API key available under LiteLLM's expected name."""
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    google_api_key = os.getenv("GOOGLE_API_KEY")

    if not gemini_api_key and google_api_key:
        os.environ["GEMINI_API_KEY"] = google_api_key


def get_raw_model_name() -> str:
    """Return the model configured in the environment, without adding prefixes."""
    return os.getenv("AGENCY_MODEL", DEFAULT_AGENCY_MODEL).strip()


def normalize_gemini_model_name(model_name: str) -> str:
    """Return a Gemini LiteLLM model name without the leading litellm/ prefix."""
    normalized = model_name.strip()

    if normalized.startswith(LITELLM_PREFIX):
        normalized = normalized.removeprefix(LITELLM_PREFIX)

    if normalized.startswith("models/"):
        normalized = normalized.removeprefix("models/")

    if not normalized.startswith(GEMINI_PROVIDER_PREFIX):
        normalized = f"{GEMINI_PROVIDER_PREFIX}{normalized}"

    return normalized


def get_model_name() -> str:
    """Return the configured model name in Agency Swarm's LiteLLM format."""
    return f"{LITELLM_PREFIX}{normalize_gemini_model_name(get_raw_model_name())}"


def get_litellm_completion_model() -> str:
    """Return the model name in the format expected by LiteLLM completion."""
    return normalize_gemini_model_name(get_raw_model_name())


def get_gemini_api_key() -> str | None:
    """Return the configured Gemini API key, if one is present."""
    configure_gemini_environment()
    return os.getenv("GEMINI_API_KEY")


def require_gemini_api_key() -> str:
    """Return the Gemini API key or raise a clear setup error."""
    api_key = get_gemini_api_key()

    if not api_key or api_key in GEMINI_API_KEY_PLACEHOLDERS:
        raise RuntimeError(
            "Gemini API key is missing. Add it to .env as "
            "GEMINI_API_KEY=your-real-key."
        )

    return api_key


configure_gemini_environment()
