"""
Secrets adapter: maps Streamlit st.secrets (or environment) into Settings.

Settings remains the single configuration source.
This adapter is the only place that may touch st.secrets.
"""

from __future__ import annotations

import os
from typing import Any, Mapping


def apply_streamlit_secrets(secrets: Mapping[str, Any] | None = None) -> None:
    """
    Inject Streamlit secrets into environment variables so that
    pydantic-settings picks them up on the next Settings() construction.

    Call AFTER st.set_page_config() to avoid SessionInfo initialization errors.
    """
    if secrets is None:
        try:
            import streamlit as st

            # Guard: only read if secrets are available; never crash app startup
            secrets = dict(st.secrets)  # type: ignore[arg-type]
        except Exception:
            return

    if not secrets:
        return

    mapping = {
        "YOUTUBE_API_KEY": ["YOUTUBE_API_KEY", "youtube_api_key"],
        "REDDIT_CLIENT_ID": ["REDDIT_CLIENT_ID", "reddit_client_id"],
        "REDDIT_CLIENT_SECRET": ["REDDIT_CLIENT_SECRET", "reddit_client_secret"],
        "REDDIT_USER_AGENT": ["REDDIT_USER_AGENT", "reddit_user_agent"],
        "SUPABASE_URL": ["SUPABASE_URL", "supabase_url"],
        "SUPABASE_KEY": ["SUPABASE_KEY", "supabase_key", "SUPABASE_ANON_KEY"],
        "SUPABASE_BUCKET": ["SUPABASE_BUCKET", "supabase_bucket"],
        "GOOGLE_TRENDS_GEO": ["GOOGLE_TRENDS_GEO"],
        "GOOGLE_TRENDS_LANGUAGE": ["GOOGLE_TRENDS_LANGUAGE"],
        "ATLAS_ENV": ["ATLAS_ENV"],
        "ATLAS_LOG_LEVEL": ["ATLAS_LOG_LEVEL"],
    }

    # Support both flat and nested secret maps
    flat: dict[str, Any] = {}
    for k, v in secrets.items():
        if isinstance(v, Mapping):
            for nk, nv in v.items():
                flat[str(nk)] = nv
                flat[f"{k}.{nk}"] = nv
        else:
            flat[str(k)] = v

    lower_map = {k.lower(): v for k, v in flat.items()}

    for env_key, possible_names in mapping.items():
        if os.environ.get(env_key):
            continue
        for name in possible_names:
            if name in flat and flat[name] is not None and str(flat[name]).strip():
                os.environ[env_key] = str(flat[name])
                break
            if name.lower() in lower_map and lower_map[name.lower()] is not None:
                val = lower_map[name.lower()]
                if str(val).strip():
                    os.environ[env_key] = str(val)
                    break
