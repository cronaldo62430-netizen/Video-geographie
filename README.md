# Vidéos géo/histoire générées par IA

Chaque jour, le pipeline produit une vidéo verticale (~1 min) :
1. **Claude** choisit un sujet inédit, écrit le scénario (scènes, cartes, textes) puis revérifie les faits.
2. La **voix off** est générée en local sur ton GPU avec OmniVoice (moteur de VoiceStudio, code Apache 2.0, poids CC-BY-NC : usage non commercial), ou par ElevenLabs si `tts_engine` vaut `elevenlabs`.
3. Les **cartes** (relief satellite Natural Earth + vraies frontières) sont animées par code : pays colorés, zoom, labels, sous-titres.
4. Les scènes historiques utilisent des **images IA** (OpenAI `gpt-image-1`), avec repli sur une carte si absent.
5. `ffmpeg` assemble le MP4 (720x1280, 30 fps).

## Installation
```
pip install -r requirements.txt
export ANTHROPIC_API_KEY=... ELEVENLABS_API_KEY=... OPENAI_API_KEY=...
python -m src.main                 # vidéo complète
python -m src.main --theme histoire
python -m src.main --script examples_congo.json --no-voice   # test sans clés
```
Résultat dans `output/<date>/` : `video.mp4`, `caption.txt` (légende + hashtags), `script.json`.

## Voix locale (gratuit, GPU)
```
pip install torch==2.8.0+cu128 torchaudio==2.8.0+cu128 --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt -r requirements-local.txt
```
`config.json` : `"tts_engine": "omnivoice"`. Voix décrite via `omnivoice.instruct` (en anglais, ex. `"male, moderate pitch"`)
ou clonée via `ref_audio` + `ref_text` (uniquement une voix dont tu as les droits). Pour forcer ElevenLabs : `TTS_ENGINE=elevenlabs`.
Non testé ici (pas de GPU) : vérifie d'abord la qualité du français sur quelques phrases.
Planification quotidienne sur ton PC : Planificateur de tâches Windows (ou cron) lançant `python -m src.main`.

## Automatisation quotidienne (GitHub Actions, sans GPU)
Le workflow n'a pas de GPU : il utilise donc ElevenLabs (`TTS_ENGINE=elevenlabs`).
Ajoute les 3 clés dans *Settings > Secrets and variables > Actions*
(`ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `OPENAI_API_KEY`).
Le workflow `.github/workflows/daily.yml` tourne à 06:00 UTC et crée une **Release** contenant la vidéo et sa légende :
ouvre GitHub sur ton téléphone, télécharge, poste sur TikTok (~30 s).

## Personnalisation
`config.json` : pseudo affiché, voix ElevenLabs, thèmes, modèle Claude.
Musique de fond optionnelle : dépose un fichier `assets/music.mp3` (libre de droits).
