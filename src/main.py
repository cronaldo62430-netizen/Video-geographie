"""Pipeline complet : sujet -> scénario -> voix -> visuels -> vidéo MP4."""
import argparse
import json
import random
import subprocess
import time
from datetime import date
from pathlib import Path

import imageio_ffmpeg

from . import voice
from .geo import World
from .images import generate_image
from .render import Renderer

ROOT = Path(__file__).resolve().parent.parent
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def encode(renderer: Renderer, states, durations, workdir: Path, out: Path, outro_len=1.5):
    W, H, fps = renderer.W, renderer.H, renderer.fps
    music = next(iter(sorted((ROOT / "assets").glob("music.*"))), None)
    cmd = [FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
           "-i", str(workdir / "voice.wav")]
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(music), "-filter_complex",
                "[2:a]volume=0.10[m];[1:a][m]amix=inputs=2:duration=first:normalize=0[a]", "-map", "0:v", "-map", "[a]"]
    else:
        cmd += ["-map", "0:v", "-map", "1:a"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    total = 0
    for st, dur in zip(states, durations):
        n = int(round(dur * fps))
        for f in range(n):
            proc.stdin.write(renderer.frame(st, f / fps, dur).tobytes())
        total += n
        print(f"  scène rendue ({dur:.1f}s)")
    # la voix se termine ; l'outro est muet, on laisse -shortest couper à la fin de l'audio
    proc.stdin.close()
    proc.wait()
    if proc.returncode:
        raise RuntimeError("ffmpeg a échoué")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", help="utiliser un scénario JSON existant (sinon Claude en génère un)")
    ap.add_argument("--theme", help="forcer un thème")
    ap.add_argument("--no-voice", action="store_true", help="voix muette (tests sans clé ElevenLabs)")
    ap.add_argument("--no-verify", action="store_true", help="sauter la passe de vérification des faits")
    ap.add_argument("--max-scenes", type=int, help="limiter le nombre de scènes (tests)")
    args = ap.parse_args()

    cfg = json.loads((ROOT / "config.json").read_text())
    hist_path = ROOT / "history.json"
    history = json.loads(hist_path.read_text())

    if args.script:
        script = json.loads(Path(args.script).read_text())
    else:
        from .script_gen import generate_script
        theme = args.theme or random.choice(cfg["themes"])
        print(f"Génération du scénario ({theme})...")
        script = generate_script(cfg, theme, [h["topic"] for h in history], verify=not args.no_verify)

    scenes = script["scenes"][: args.max_scenes] if args.max_scenes else script["scenes"]
    out_dir = ROOT / "output" / f"{date.today().isoformat()}-{int(time.time()) % 100000}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "script.json").write_text(json.dumps(script, ensure_ascii=False, indent=2))

    print("Voix off...")
    durations = voice.build_voice(scenes, out_dir, cfg, silent=args.no_voice)
    print(f"Durée totale : {sum(durations):.1f}s")

    print("Images IA...")
    for i, sc in enumerate(scenes):
        v = sc.get("visual", {})
        if v.get("type") == "image":
            generate_image(v["prompt"], out_dir / f"img{i:02d}.png", cfg)

    print("Rendu vidéo...")
    world = World()
    renderer = Renderer(cfg, world)
    states = [renderer.prepare(sc, i, out_dir) for i, sc in enumerate(scenes)]
    video = out_dir / "video.mp4"
    encode(renderer, states, durations, out_dir, video)

    caption = f"{script['caption']}\n\n{' '.join(script.get('hashtags', []))}"
    (out_dir / "caption.txt").write_text(caption)
    if not args.script:
        history.append({"date": date.today().isoformat(), "topic": script.get("topic", script["title"])})
        hist_path.write_text(json.dumps(history, ensure_ascii=False, indent=2))
    print(f"\nTerminé : {video}\nLégende : {out_dir / 'caption.txt'}")


if __name__ == "__main__":
    main()
