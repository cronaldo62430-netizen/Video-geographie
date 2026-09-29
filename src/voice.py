"""Voix off (ElevenLabs) et utilitaires audio."""
import os
import subprocess
import wave
from pathlib import Path

import imageio_ffmpeg
import requests

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def to_wav(src: Path, dst: Path, pad: float = 0.0) -> None:
    af = f"apad=pad_dur={pad}" if pad else "anull"
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", str(src), "-af", af, "-ar", "44100", "-ac", "2", str(dst)], check=True)


def wav_duration(p: Path) -> float:
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


def silent_wav(dst: Path, seconds: float) -> None:
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"\x00" * int(seconds * 44100) * 4)


def synthesize(text: str, dst_mp3: Path, cfg: dict) -> None:
    key = os.environ["ELEVENLABS_API_KEY"]
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{cfg['elevenlabs_voice_id']}?output_format=mp3_44100_128",
        headers={"xi-api-key": key, "Content-Type": "application/json"},
        json={"text": text, "model_id": cfg["elevenlabs_model"],
              "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.35, "speed": 1.08}},
        timeout=120,
    )
    r.raise_for_status()
    dst_mp3.write_bytes(r.content)


def build_voice(scenes: list[dict], workdir: Path, cfg: dict, silent: bool) -> list[float]:
    """Génère l'audio de chaque scène ; renvoie les durées (s) et écrit workdir/voice.wav."""
    gap = 0.3
    wavs, durations = [], []
    for i, sc in enumerate(scenes):
        wav = workdir / f"s{i:02d}.wav"
        if silent:
            silent_wav(wav, max(2.0, len(sc["narration"]) / 15) + gap)
        else:
            mp3 = workdir / f"s{i:02d}.mp3"
            synthesize(sc["narration"], mp3, cfg)
            to_wav(mp3, wav, pad=gap)
        wavs.append(wav)
        durations.append(wav_duration(wav))
    with wave.open(str(workdir / "voice.wav"), "wb") as out:
        for j, w in enumerate(wavs):
            with wave.open(str(w)) as src:
                if j == 0:
                    out.setparams(src.getparams())
                out.writeframes(src.readframes(src.getnframes()))
    return durations
