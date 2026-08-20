from __future__ import annotations
from hashlib import sha256
from importlib.resources import files

def consumer_policy() -> str:
    text = files("knowledge_integration").joinpath("consumer-policy.md").read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError("packaged consumer policy must not be empty")
    return text

def consumer_policy_fingerprint() -> str:
    return sha256(consumer_policy().encode("utf-8")).hexdigest()
