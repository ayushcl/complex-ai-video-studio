"""Smoke-test the Gemini/LiteLLM connection for the video generation agency."""

from __future__ import annotations

from litellm import completion
from litellm.exceptions import AuthenticationError, NotFoundError, PermissionDeniedError

from video_generation_agency.settings import (
    get_litellm_completion_model,
    get_model_name,
    normalize_gemini_model_name,
    require_gemini_api_key,
)

FALLBACK_MODEL = "gemini-2.0-flash"
MAX_OUTPUT_TOKENS = 80
SUGGESTED_ENV_MODELS = (
    "gemini-2.5-flash",
    FALLBACK_MODEL,
)


def run_completion(model_name: str) -> str:
    response = completion(
        model=model_name,
        messages=[
            {
                "role": "user",
                "content": "Reply with exactly: Gemini connection OK",
            }
        ],
        max_tokens=MAX_OUTPUT_TOKENS,
        timeout=60,
    )

    message = response["choices"][0]["message"]["content"]
    if not message:
        raise RuntimeError(
            "Gemini returned no text content. The request authenticated, but "
            "the response did not include a final assistant message."
        )

    return message


def main() -> int:
    try:
        require_gemini_api_key()
    except RuntimeError as exc:
        print(exc)
        print("Put the key in .env, then rerun this script.")
        return 2

    completion_model = get_litellm_completion_model()
    print(f"Agency model: {get_model_name()}")
    print(f"LiteLLM model: {completion_model}")

    try:
        message = run_completion(completion_model)
    except NotFoundError as exc:
        print(f"Model not found or not enabled: {get_model_name()}")
        fallback_model = normalize_gemini_model_name(FALLBACK_MODEL)

        if completion_model != fallback_model:
            print(f"Trying fallback model: {fallback_model}")
            try:
                message = run_completion(fallback_model)
            except NotFoundError:
                print("Fallback model is also unavailable.")
                print(f"Use one of these AGENCY_MODEL values: {SUGGESTED_ENV_MODELS}")
                print(exc)
                return 3
        else:
            print(f"Use one of these AGENCY_MODEL values: {SUGGESTED_ENV_MODELS}")
            print(exc)
            return 3
    except AuthenticationError as exc:
        print("Gemini authentication failed. Check GEMINI_API_KEY in local .env.")
        print(exc)
        return 4
    except PermissionDeniedError as exc:
        print("Gemini access denied. Check API permissions, billing, and model access.")
        print(exc)
        return 5
    except RuntimeError as exc:
        print(exc)
        return 6

    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
