"""Illustrations générées par IA (OpenAI gpt-image-1) pour les scènes historiques."""
import base64
import os
from pathlib import Path

import requests

STYLE = " Cinematic, dramatic lighting, detailed historical illustration, vertical composition, no text, no letters, no watermark."


def generate_image(prompt: str, dst: Path, cfg: dict) -> bool:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return False
    try:
        r = requests.post(
            "https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": cfg["image_model"], "prompt": prompt + STYLE, "size": "1024x1536", "n": 1},
            timeout=180,
        )
        r.raise_for_status()
        dst.write_bytes(base64.b64decode(r.json()["data"][0]["b64_json"]))
        return True
    except Exception as e:
        print(f"Image IA échouée ({e}) — repli sur une carte.")
        return False
