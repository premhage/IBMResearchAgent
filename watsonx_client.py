"""
watsonx_client.py — IBM watsonx.ai client using direct REST API.

The IBM watsonx-ai SDK validates project membership via /v2/projects
before allowing any calls.  For Studio-managed projects (au-syd) the
SDK list endpoint returns 404 while the generation endpoint works fine.
This module uses direct REST calls which bypass that validation step.

Confirmed working with:
  model   : ibm/granite-8b-code-instruct  (au-syd)
  project : 3c059543-877b-400e-8cb5-3847ebb295ff
"""
from __future__ import annotations

import os
import time
from typing import Any, Optional

import requests

from config import (
    GRANITE_EMBED_ID,
    GRANITE_MODEL_ID,
    WATSONX_API_KEY,
    WATSONX_PROJECT_ID,
    WATSONX_URL,
)

# ─────────────────────────────────────────────────────────────────────────────
#  IAM Token cache
# ─────────────────────────────────────────────────────────────────────────────

_token_cache: dict[str, Any] = {"token": None, "expires_at": 0.0}


def _get_iam_token() -> str:
    """Fetch (or return cached) IBM IAM bearer token."""
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    resp = requests.post(
        "https://iam.cloud.ibm.com/identity/token",
        data={
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
            "apikey": WATSONX_API_KEY,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    _token_cache["token"]      = data["access_token"]
    _token_cache["expires_at"] = now + int(data.get("expires_in", 3600))
    return _token_cache["token"]


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_get_iam_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Text generation
# ─────────────────────────────────────────────────────────────────────────────

def generate(
    prompt: str,
    max_new_tokens: int = 1024,
    temperature: float = 0.3,
    stop_sequences: Optional[list[str]] = None,
) -> str:
    """Generate text via Granite REST API — returns raw string."""
    if not is_configured():
        return _mock_generate(prompt)

    url = f"{WATSONX_URL}/ml/v1/text/generation?version=2023-05-29"
    payload: dict[str, Any] = {
        "model_id": GRANITE_MODEL_ID,
        "project_id": WATSONX_PROJECT_ID,
        "input": prompt,
        "parameters": {
            "max_new_tokens": max_new_tokens,
            "temperature": temperature,
            "repetition_penalty": 1.1,
        },
    }
    if stop_sequences:
        payload["parameters"]["stop_sequences"] = stop_sequences

    try:
        resp = requests.post(url, headers=_headers(), json=payload, timeout=120)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if results:
            return results[0].get("generated_text", "")
        return ""
    except requests.HTTPError as exc:
        try:
            msg = exc.response.json().get("errors", [{}])[0].get("message", str(exc))
        except Exception:
            msg = str(exc)
        return f"[GENERATION ERROR] {msg}"
    except Exception as exc:
        return f"[GENERATION ERROR] {exc}"


# ─────────────────────────────────────────────────────────────────────────────
#  Embeddings  (try SDK first; fall back to TF-IDF in knowledge_base.py)
# ─────────────────────────────────────────────────────────────────────────────

def embed(texts: list[str]) -> list[list[float]]:
    """
    Return embedding vectors.
    Tries the watsonx embedding REST endpoint; falls back to mock hashes.
    """
    if not is_configured():
        return _mock_embed(texts)

    url = f"{WATSONX_URL}/ml/v1/text/embeddings?version=2023-05-29"
    payload: dict[str, Any] = {
        "model_id": GRANITE_EMBED_ID,
        "project_id": WATSONX_PROJECT_ID,
        "inputs": texts,
    }
    try:
        resp = requests.post(url, headers=_headers(), json=payload, timeout=60)
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            return [r.get("embedding", []) for r in results]
        # Embedding model not available in this region — use mock
        return _mock_embed(texts)
    except Exception:
        return _mock_embed(texts)


# ─────────────────────────────────────────────────────────────────────────────
#  Status check
# ─────────────────────────────────────────────────────────────────────────────

def is_configured() -> bool:
    return bool(WATSONX_API_KEY and WATSONX_PROJECT_ID)


def ping() -> bool:
    """Return True if we can get an IAM token and reach the generation endpoint."""
    try:
        _get_iam_token()
        url = f"{WATSONX_URL}/ml/v1/foundation_model_specs?version=2024-09-16"
        resp = requests.get(url, headers=_headers(), timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
#  Mock fallbacks (for development without credentials)
# ─────────────────────────────────────────────────────────────────────────────

def _mock_generate(prompt: str) -> str:
    return (
        "[MOCK RESPONSE — configure WATSONX_API_KEY in .env]\n\n"
        "Thought: I need to analyse the provided context.\n"
        "Action: search_kb(query='rover navigation SLAM')\n"
        "Observation: [KB] Found 2 relevant chunks from uploaded papers.\n"
        "Thought: The papers discuss path planning but lack RL benchmarks.\n"
        "Action: exa_search(query='reinforcement learning rover navigation 2024')\n"
        "Observation: [WEB] Retrieved 3 live results from Exa.\n"
        "Thought: I can now synthesise the answer.\n"
        "Final Answer: [INFER] Based on the knowledge base and live search, "
        "a key research gap exists in applying sim-to-real RL transfer for "
        "unstructured outdoor terrain. [LOW-CONFIDENCE]\n\n"
        "**References**\n"
        "[1] Mock Author, 'Mock Title,' Mock Journal, 2024."
    )


def _mock_embed(texts: list[str]) -> list[list[float]]:
    import hashlib
    import math
    result = []
    for text in texts:
        h = int(hashlib.md5(text.encode()).hexdigest(), 16)
        vec = [(math.sin(h + i) + 1) / 2 for i in range(128)]
        result.append(vec)
    return result
