from __future__ import annotations

import os
from typing import Dict, Optional

import requests

try:
    import msal  # type: ignore
except Exception:  # pragma: no cover
    msal = None  # type: ignore


DEFAULT_SCOPES = [
    "openid",
    "profile",
    "offline_access",
    "User.Read",
]


def _get_secret(name: str, default: str = "") -> str:
    try:
        import streamlit as st  # type: ignore

        if hasattr(st, "secrets") and name in st.secrets:  # type: ignore
            return str(st.secrets.get(name) or "")
    except Exception:
        pass
    return os.getenv(name, default)


def load_config() -> Dict[str, str]:
    return {
        "client_id": _get_secret("AZURE_CLIENT_ID"),
        "tenant_id": _get_secret("AZURE_TENANT_ID", "common"),
        "client_secret": _get_secret("AZURE_CLIENT_SECRET"),
        "redirect_uri": _get_secret("AZURE_REDIRECT_URI", "http://localhost:8501"),
    }


def build_app(conf: Dict[str, str], cache=None):
    if msal is None:
        raise RuntimeError("msal package not installed. Add 'msal' to requirements.txt")
    authority = f"https://login.microsoftonline.com/{conf.get('tenant_id') or 'common'}"
    return msal.ConfidentialClientApplication(
        client_id=conf.get("client_id") or "",
        client_credential=conf.get("client_secret") or "",
        authority=authority,
        token_cache=cache,
    )


def build_auth_url(app, scopes: Optional[list[str]] = None, redirect_uri: Optional[str] = None) -> str:
    scopes = scopes or DEFAULT_SCOPES
    return app.get_authorization_request_url(scopes=scopes, redirect_uri=redirect_uri)


def exchange_code_for_token(app, code: str, scopes: Optional[list[str]], redirect_uri: str) -> Dict:
    scopes = scopes or DEFAULT_SCOPES
    return app.acquire_token_by_authorization_code(code, scopes=scopes, redirect_uri=redirect_uri)


def get_me(access_token: str) -> Dict:
    resp = requests.get(
        "https://graph.microsoft.com/v1.0/me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


# Optional: persistent token cache helpers
def get_serializable_cache(cache_path: str):
    if msal is None:
        return None
    cache = msal.SerializableTokenCache()
    try:
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as fh:
                cache.deserialize(fh.read())
    except Exception:
        # Corrupt cache: start fresh
        cache = msal.SerializableTokenCache()
    return cache


def save_cache(cache, cache_path: str) -> None:
    try:
        if cache and getattr(cache, "has_state_changed", False):
            os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as fh:
                fh.write(cache.serialize())
    except Exception:
        # Best-effort; ignore persistence errors
        pass
