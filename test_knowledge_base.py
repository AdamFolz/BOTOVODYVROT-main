#!/usr/bin/env python3
"""Check the local OPENAI_API_KEY without printing the secret."""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from openai import AuthenticationError, OpenAI


def mask_key(key: str) -> str:
    if len(key) <= 12:
        return "<too-short>"
    return f"{key[:7]}...{key[-4:]}"


def main() -> int:
    load_dotenv()
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    base_url = (os.getenv("OPENAI_BASE_URL") or "").strip()

    if not key:
        print("OPENAI_API_KEY is missing in .env")
        return 2

    print(f"OPENAI_API_KEY found: {mask_key(key)}")
    if base_url:
        print(f"OPENAI_BASE_URL: {base_url}")

    if not key.startswith("sk-"):
        print("Warning: key does not start with 'sk-'. Check that you copied the API key, not another token.")

    if any(char.isspace() for char in key):
        print("Warning: key contains whitespace. Remove spaces/newlines from OPENAI_API_KEY in .env.")
        return 2

    try:
        client = OpenAI(api_key=key, base_url=base_url or None)
        models = client.models.list()
    except AuthenticationError:
        print("Provider rejected this key: 401 Unauthorized / invalid API key.")
        print("Create a new key, replace OPENAI_API_KEY in .env, stop the bot, and start it again.")
        return 3
    except Exception as exc:
        print(f"OpenAI key check failed with a non-auth error: {exc}")
        return 4

    first_model = models.data[0].id if models.data else "<no models returned>"
    print(f"OpenAI key is valid. Example visible model: {first_model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
