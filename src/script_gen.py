"""Génération du scénario de la vidéo avec l'API Claude."""
import json
import os
import re
import shutil
import subprocess

SYSTEM = """Tu es scénariste de vidéos TikTok éducatives (~1 minute) sur la géographie et l'histoire, \
dans le style de "La Minute Géographie" : un fait surprenant, expliqué de façon claire, rythmée et visuelle. \
Tu réponds UNIQUEMENT avec un objet JSON valide, sans texte autour."""

PROMPT = """Crée le scénario d'une vidéo verticale d'environ une minute, en {language}.

Thème du jour : {theme}
Sujets DÉJÀ traités (à ne PAS répéter) : {history}

Règles de narration :
- Accroche choc dans la première phrase (question ou fait surprenant), chute/révélation à la fin.
- Environ {words} mots au total, phrases courtes, ton oral et vivant, tutoiement ou "on" possible.
- Faits STRICTEMENT exacts et vérifiables (dates, chiffres, noms). En cas de doute, ne pas l'inclure.
- 12 à 16 scènes, chacune = 1 à 2 phrases (max ~18 mots), enchaînées naturellement.

Chaque scène a un visuel :
- "map" : carte satellite. Champs :
    "zoom": liste de codes pays ISO alpha-3 sur lesquels cadrer la caméra (ex ["COD","COG"]) ;
       [] = vue du monde ; ou "bbox": [lon_min, lat_min, lon_max, lat_max] pour cadrer une région précise
    "highlight": liste d'objets {{"country":"COD","color":"red|blue|green|yellow|purple|orange"}}
    "labels": liste d'objets {{"country":"COD","text":"RD Congo"}} (texte court)
    "markers": liste d'objets {{"lon":15.3,"lat":-4.3,"text":"Kinshasa"}}
- "image" : illustration générée par IA, pour les scènes historiques/humaines (portrait, bataille, objet). \
    Champ "prompt" : description visuelle en anglais, réaliste, sans texte dans l'image, sans personne réelle vivante.
Alterne cartes (majoritaires) et 2 à 4 images. Les pays historiques disparus se montrent en colorant \
les pays actuels qui les composent.

"text" (optionnel) : gros titre à l'écran (max 4 mots), pour les moments clés (nom, date, chiffre).

Format JSON exact :
{{
  "topic": "sujet en une ligne",
  "title": "titre accrocheur de la vidéo",
  "caption": "description TikTok (1-2 phrases + question pour engager)",
  "hashtags": ["#geographie", "#histoire", "..."],
  "scenes": [
    {{"narration": "...", "text": "...", "visual": {{"type": "map", "zoom": ["COD"], "highlight": [], "labels": [], "markers": []}}}}
  ]
}}"""

VERIFY = """Voici le scénario JSON d'une vidéo éducative. Vérifie chaque fait (dates, chiffres, noms, géographie). \
Corrige toute erreur ou approximation dans "narration", "text" et "caption". Ne change pas la structure ni les visuels, \
sauf si un visuel contredit un fait corrigé. Renvoie UNIQUEMENT le JSON complet corrigé.

{script}"""


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("Pas de JSON dans la réponse de Claude")
    return json.loads(m.group(0))


def _ask_cli(model, system, prompt):
    """Utilise le CLI Claude Code connecté à ton abonnement (`claude login`), sans clé API."""
    exe = shutil.which("claude")
    if not exe:
        raise RuntimeError("CLI `claude` introuvable : installe Claude Code et lance `claude login`, ou définis ANTHROPIC_API_KEY.")
    r = subprocess.run([exe, "-p", "--model", model, "--append-system-prompt", system, "--output-format", "text"],
                       input=prompt, capture_output=True, text=True, timeout=600)
    if r.returncode:
        raise RuntimeError(f"claude -p a échoué : {r.stderr.strip()[:500]}")
    return r.stdout


def _ask(client, model, system, prompt, max_tokens=8000):
    if client is None:
        return _ask_cli(model, system, prompt)
    msg = client.messages.create(
        model=model, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in msg.content if b.type == "text")


def generate_script(cfg: dict, theme: str, history: list[str], verify: bool = True) -> dict:
    # Sans clé API, on passe par le CLI Claude Code (abonnement). Forçable avec CLAUDE_BACKEND=api|cli.
    backend = os.environ.get("CLAUDE_BACKEND") or ("api" if os.environ.get("ANTHROPIC_API_KEY") else "cli")
    if backend == "api":
        import anthropic
        client = anthropic.Anthropic()
    else:
        client = None
    model = cfg["claude_model"]
    prompt = PROMPT.format(
        language="français" if cfg["language"] == "fr" else cfg["language"],
        theme=theme, history=", ".join(history[-60:]) or "aucun", words=cfg["target_words"],
    )
    script = _extract_json(_ask(client, model, SYSTEM, prompt))
    if verify:
        script = _extract_json(_ask(client, model, SYSTEM, VERIFY.format(script=json.dumps(script, ensure_ascii=False))))
    return script
