"""
Thin wrapper around the OpenRouter chat-completions API.

OpenRouter speaks the OpenAI-compatible /chat/completions schema, so this
is a plain `requests` call — no special SDK needed.
"""
import json
import re
import requests
import streamlit as st

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# A solid default. Users can override via secrets.toml / env / sidebar.
DEFAULT_MODEL = "anthropic/claude-3.5-sonnet"


def _get_api_key() -> str:
    key = st.secrets.get("OPENROUTER_API_KEY", "") if hasattr(st, "secrets") else ""
    if not key:
        import os
        key = os.environ.get("OPENROUTER_API_KEY", "")
    return key


def _get_model() -> str:
    if hasattr(st, "secrets") and st.secrets.get("OPENROUTER_MODEL"):
        return st.secrets["OPENROUTER_MODEL"]
    return st.session_state.get("model_override") or DEFAULT_MODEL


class LLMError(Exception):
    pass


def call_llm(prompt: str, max_tokens: int = 800, temperature: float = 0.7) -> str:
    """Send a single-turn prompt to the configured OpenRouter model and
    return the assistant's text reply."""
    api_key = _get_api_key()
    if not api_key:
        raise LLMError(
            "No OpenRouter API key found. Add OPENROUTER_API_KEY to "
            ".streamlit/secrets.toml (locally) or to your app's Secrets "
            "(on Streamlit Community Cloud)."
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        # These two headers are optional but recommended by OpenRouter.
        "HTTP-Referer": "https://github.com/",
        "X-Title": "Talk It Out - Voice Journal",
    }
    payload = {
        "model": _get_model(),
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=60)
    except requests.RequestException as e:
        raise LLMError(f"Couldn't reach OpenRouter — check your connection. ({e})")

    if resp.status_code == 401:
        raise LLMError("OpenRouter rejected the API key (401). Double-check the secret.")
    if resp.status_code == 429:
        raise LLMError("Rate limited by OpenRouter (429). Wait a bit and try again.")
    if not resp.ok:
        raise LLMError(f"OpenRouter error {resp.status_code}: {resp.text[:300]}")

    try:
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise LLMError(f"Got an unreadable response from OpenRouter. ({e})")


def safe_parse_json(text: str):
    """Mirror of the original app's tolerant JSON parser: strips ```json
    fences and falls back to None on failure."""
    if not text:
        return None
    cleaned = text.strip()
    cleaned = re.sub(r"^```json", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"^```", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # try to grab the first {...} block as a last resort
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
        return None
