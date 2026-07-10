#!/usr/bin/env python3
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from openai import AsyncOpenAI

async def main():
    print("Provider:", config.provider_info())
    if not config.LLM.api_key:
        print("❌ API key missing"); sys.exit(2)
    client = AsyncOpenAI(api_key=config.LLM.api_key, base_url=config.LLM.base_url or None, default_headers=config.LLM.extra_headers or None)
    try:
        extra = {}
        if config.LLM.extra_body:
            extra["extra_body"] = config.LLM.extra_body
        r = await client.chat.completions.create(
            model=config.LLM.model,
            messages=[{"role":"user","content":"ping"}],
            max_tokens=5,
            temperature=0,
            **extra
        )
        print("✅ OK:", r.choices[0].message.content)
    except Exception as e:
        print("❌ FAIL:", e)
        print("\nСоветы:")
        print("- Проверь OPENAI_BASE_URL заканчивается на /v1")
        print("- Venice: base_url=https://api.venice.ai/api/v1 model=qwen3-4b")
        print("- KIMI Code: base_url=https://api.kimi.com/coding/v1 model=kimi-k2.7-code")
        print("- Moonshot: base_url=https://api.moonshot.ai/v1 model=moonshot-v1-8k")
        print("- Proxy vip.j3gb.com: OPENAI_BASE_URL=https://vip.j3gb.com/v1")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
