import os
import sys
import re
import json
import base64
import time
import socket
import urllib.request
import urllib.error
from pathlib import Path
from typing import List, Dict, Any, Optional

from config import (
    GEMINI_KEYS_FILE,
    GEMINI_MODEL,
    CHANNEL_NAME
)

socket.setdefaulttimeout(60)

def load_keys() -> List[str]:
    keys = []
    if GEMINI_KEYS_FILE.exists():
        with open(GEMINI_KEYS_FILE, "r", encoding="utf-8") as f:
            keys = [k.strip() for k in f if k.strip() and not k.startswith("#")]
    env_key = os.environ.get("GEMINI_API_KEY", "")
    if env_key and env_key not in keys:
        keys.append(env_key.strip())
    if not keys:
        raise ValueError("Aucune clé API Gemini disponible.")
    return keys

_KEYS = load_keys()
_KI = [0]
STATS = {"calls": 0, "rotations": 0, "failures": 0}

def call_gemini(parts: List[Dict[str, Any]], model: str = GEMINI_MODEL, retries: int = 8, initial_backoff: int = 10) -> str:
    """Appel hautement résilient à Gemini avec rotation automatique des clés et backoff exponentiel."""
    data = json.dumps({
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 4096
        }
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    for rnd in range(retries):
        for _ in range(max(1, len(_KEYS))):
            key = _KEYS[_KI[0] % len(_KEYS)]
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            try:
                req = urllib.request.Request(url, data=data, headers=headers)
                with urllib.request.urlopen(req, timeout=60) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                STATS["calls"] += 1
                candidates = result.get("candidates", [])
                if candidates and "content" in candidates[0]:
                    return "".join(p.get("text", "") for p in candidates[0]["content"].get("parts", [])).strip()
                return ""
            except urllib.error.HTTPError as e:
                _KI[0] += 1
                if e.code in (429, 503, 500):
                    STATS["rotations"] += 1
                    time.sleep(1.5)
                    continue
                err_text = e.read().decode("utf-8", "ignore")[:200]
                print(f"[Gemini] HTTPError {e.code}: {err_text}", flush=True)
            except Exception as e:
                _KI[0] += 1
                time.sleep(2)

        wait_s = initial_backoff * (rnd + 1)
        print(f"[Gemini] Quotas temporairement atteints. Pause {wait_s}s (essai {rnd+1}/{retries})...", flush=True)
        time.sleep(wait_s)

    STATS["failures"] += 1
    return ""

def translate_title_fr(title_en: str) -> str:
    """Traduit le titre anglais en français percutant et professionnel."""
    prompt = (
        "Tu es un traducteur expert en vidéo IA, infographie et cinéma numérique.\n"
        "Traduis ce titre de vidéo YouTube de l'anglais vers un français percutant, captivant et naturel.\n"
        "Garde les noms de logiciels/outils/modèles intacts (Seedance, Kling, Midjourney, Wan, Nano Banana, Claude, GPT, etc.).\n"
        "Réponds STRICTEMENT avec le titre traduit uniquement, sans guillemets ni fioritures.\n\n"
        f"Titre : {title_en}"
    )
    res = call_gemini([{"text": prompt}])
    return res.strip().replace('"', '') if res else title_en

def process_multimodal_block(
    candidate_frames: List[Dict[str, Any]],
    timestamp_str: str,
    text_en: str
) -> Dict[str, Any]:
    """
    Analyse multimodale chirurgicale d'un bloc temporel :
    1. Traduction mot à mot intégrale (verbatim) en français sans coupure.
    2. Filtrage strict anti-talking-head : Détecte et élimine les images montrant uniquement le youtubeur qui parle face caméra sans écran partagé.
    3. Retient TOUTES les images de vraies démonstrations (interfaces, prompts, workflows, rendus IA, etc.) avec légendes précises.
    4. Analyse technique des outils, paramètres et actions.
    """
    default_res = {
        "verbatim_fr": text_en,
        "valid_frame_indices": [],
        "frame_captions": {},
        "interface": "le créateur face caméra ou transition sans partage d'écran.",
        "contenu": "Explications orales des concepts et des méthodes de création vidéo IA.",
        "action": "Démonstration pédagogique et présentation du workflow."
    }

    n_imgs = len(candidate_frames)
    img_list_txt = ""
    if n_imgs > 0:
        lines = []
        for i, cf in enumerate(candidate_frames):
            lines.append(f"- Image #{i+1} : horodatage @ {cf.get('timestamp_str', '')}")
        img_list_txt = "\n".join(lines)

    prompt = (
        f"Tu es un analyste expert en vidéo par intelligence artificielle pour la chaîne {CHANNEL_NAME} (segment {timestamp_str}).\n"
        f"Voici le discours audio anglais prononcé dans ce segment :\n"
        f'"""\n{text_en}\n"""\n\n'
    )

    if n_imgs > 0:
        prompt += (
            f"Tu as reçu {n_imgs} capture(s) d'écran candidate(s) pour ce segment :\n"
            f"{img_list_txt}\n\n"
            "DIRECTIVE ABSOLUE CONCERNANT LES IMAGES :\n"
            "L'utilisateur veut UNIQUEMENT voir ce que le créateur présente ou démontre à l'écran :\n"
            "- IMAGES VALIDES (DEMO) : Tout ce qui montre l'écran du créateur : interfaces de logiciels/outils (Seedance, Kling, Claude, Suno, Higgsfield, ComfyUI, Premiere, Photoshop, navigateurs web, etc.), prompts textuels, code, rendus de vidéos ou d'images IA générées, diapositives, animations. (Si le créateur apparaît dans un petit encadré PiP dans un coin de l'écran, l'image est VALIDE car l'écran de travail est visible).\n"
            "- IMAGES STRICTEMENT INTERDITES (SPEAKER_ONLY) : Les images montrant UNIQUEMENT le créateur face caméra en train de parler dans son studio (visage ou buste devant son micro avec étagère/néons en arrière-plan) SANS écran de logiciel ni démonstration. L'utilisateur NE VEUT PAS de ces images d'illustration face caméra.\n\n"
            "Ta mission en français :\n"
            "1. VERBATIM_FR : Traduis le discours audio mot à mot intégralement en français, naturel et fluide, sans RIEN omettre ni abréger. Si c'est musical/sans parole, indique [Séquence musicale / Démonstration sonore].\n"
            "2. VALID_IMAGES : Indique les numéros (1-indexés) des images STRICTEMENT VALIDES (DEMO), séparés par des virgules (ex: '1', '1, 2', '2, 3', ou 'AUCUNE' si toutes ne montrent que le créateur face caméra).\n"
            "3. Pour chaque image valide retenue, fournis une légende précise et concise [DESC_IMAGE_X] décrivant exactement ce qui est démontré à l'écran (ex: 'Interface de Seedance 2.5 montrant le réglage de la caméra cinématique').\n"
            "4. INTERFACE : Décris précisément les interfaces, logiciels ou sites affichés sur les images valides (ex: Seedance 2.5, Kling 3.0, Midjourney, Claude, Suno, etc. ou 'Présentation face caméra sans partage d'écran' si aucune).\n"
            "5. CONTENU : Détaille tous les textes, prompts de génération, paramètres techniques visibles sur les écrans.\n"
            "6. ACTION : Décris l'action montrée ou manipulée.\n\n"
            "Format STRICT obligatoire de ta réponse :\n"
            "[VERBATIM_FR] <traduction mot à mot complète en français>\n"
            "[VALID_IMAGES] <numéros séparés par virgule, ou AUCUNE>\n"
        )
        for i in range(n_imgs):
            prompt += f"[DESC_IMAGE_{i+1}] <légende si l'image #{i+1} est valide>\n"
        prompt += (
            "[INTERFACE] <texte>\n"
            "[CONTENU] <texte>\n"
            "[ACTION] <texte>"
        )
    else:
        prompt += (
            "Ta mission en français :\n"
            "1. VERBATIM_FR : Traduis le discours audio mot à mot intégralement en français, sans rien omettre.\n"
            "2. INTERFACE : Présentation face caméra ou transition sans écran partagé.\n"
            "3. CONTENU : Explications orales du sujet.\n"
            "4. ACTION : Présentation du workflow.\n\n"
            "Format STRICT obligatoire de ta réponse :\n"
            "[VERBATIM_FR] <texte>\n"
            "[INTERFACE] <texte>\n"
            "[CONTENU] <texte>\n"
            "[ACTION] <texte>"
        )

    parts: List[Dict[str, Any]] = [{"text": prompt}]

    for cf in candidate_frames:
        img_path = cf.get("path")
        if img_path and isinstance(img_path, Path) and img_path.exists() and img_path.stat().st_size > 0:
            try:
                with open(img_path, "rb") as f:
                    b64_img = base64.b64encode(f.read()).decode("utf-8")
                parts.append({
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": b64_img
                    }
                })
            except Exception as e:
                print(f"[Gemini Vision] Erreur lecture image {img_path}: {e}", flush=True)

    raw = call_gemini(parts)
    if not raw:
        return default_res

    res = dict(default_res)
    try:
        # 1. Extraction VERBATIM_FR
        if "[VERBATIM_FR]" in raw:
            rest_v = raw.split("[VERBATIM_FR]")[1]
            end_markers = ["[VALID_IMAGES]", "[INTERFACE]", "[CONTENU]", "[ACTION]"]
            for m in end_markers:
                if m in rest_v:
                    rest_v = rest_v.split(m)[0]
            res["verbatim_fr"] = rest_v.strip()

        # 2. Extraction VALID_IMAGES & DESC_IMAGE_X
        valid_indices = []
        frame_captions = {}
        if "[VALID_IMAGES]" in raw:
            raw_val = raw.split("[VALID_IMAGES]")[1]
            for m in ["[DESC_IMAGE_", "[INTERFACE]", "[CONTENU]", "[ACTION]"]:
                if m in raw_val:
                    raw_val = raw_val.split(m)[0]
            raw_val = raw_val.strip().upper()

            if "AUCUNE" not in raw_val and "NONE" not in raw_val and "ZERO" not in raw_val:
                if "TOUTES" in raw_val or "TOUT" in raw_val or "ALL" in raw_val:
                    valid_indices = list(range(n_imgs))
                else:
                    for token in re.findall(r'\b\d+\b', raw_val):
                        num = int(token)
                        if 1 <= num <= n_imgs:
                            valid_indices.append(num - 1)

        # Captions
        for i in range(n_imgs):
            tag = f"[DESC_IMAGE_{i+1}]"
            if tag in raw:
                part_desc = raw.split(tag)[1]
                for next_tag in [f"[DESC_IMAGE_{j+1}]" for j in range(i+1, n_imgs)] + ["[INTERFACE]", "[CONTENU]", "[ACTION]"]:
                    if next_tag in part_desc:
                        part_desc = part_desc.split(next_tag)[0]
                desc_text = part_desc.strip().lstrip(": -").strip()
                if desc_text and not desc_text.startswith("<"):
                    frame_captions[i] = desc_text

        res["valid_frame_indices"] = sorted(list(set(valid_indices)))
        res["frame_captions"] = frame_captions

        # 3. Extraction INTERFACE, CONTENU, ACTION
        if "[INTERFACE]" in raw:
            p_i = raw.split("[INTERFACE]")[1]
            if "[CONTENU]" in p_i:
                res["interface"] = p_i.split("[CONTENU]")[0].strip()
            elif "[ACTION]" in p_i:
                res["interface"] = p_i.split("[ACTION]")[0].strip()
            else:
                res["interface"] = p_i.strip()

        if "[CONTENU]" in raw:
            p_c = raw.split("[CONTENU]")[1]
            if "[ACTION]" in p_c:
                res["contenu"] = p_c.split("[ACTION]")[0].strip()
            else:
                res["contenu"] = p_c.strip()

        if "[ACTION]" in raw:
            res["action"] = raw.split("[ACTION]")[1].strip()

    except Exception as e:
        print(f"[Gemini] Erreur parsing bloc multimodal : {e}", flush=True)

    return res

def generate_executive_summary(video_title: str, full_verbatim_fr: str, tools_detected: List[str]) -> str:
    """
    Rédige la synthèse exécutive structurée :
    - ### 📌 Résumé
    - ### 🛠️ Outils, Modèles & Logiciels Présentés
    - ### 🔑 Points Clés & Enseignements Stratégiques
    """
    tools_str = ", ".join(tools_detected) if tools_detected else "Seedance 2.5, Kling 3.0, Midjourney, Vidéo IA, Motion Design"
    prompt = (
        f"Tu es un réalisateur et analyste expert en vidéo par intelligence artificielle.\n"
        f"Vidéo de {CHANNEL_NAME} intitulée : « {video_title} ».\n"
        f"Outils identifiés : {tools_str}\n\n"
        f"Transcription intégrale de la vidéo en français :\n\"\"\"\n{full_verbatim_fr[:9000]}\n\"\"\"\n\n"
        "Rédige une synthèse exécutive structurée, dense, fluide et très riche en enseignements concrets en français.\n"
        "Tu DOIS STRICTEMENT employer ces titres de niveau 3 exacts :\n"
        "### 📌 Résumé\n"
        "(2 à 3 paragraphes denses et immersifs expliquant le sujet central, les techniques innovantes, la méthode étape par étape de le créateur et les bénéfices concrets pour les créateurs de vidéo)\n\n"
        "### 🛠️ Outils, Modèles & Logiciels Présentés\n"
        "(Liste à puces exhaustive avec nom de l'outil en gras et une phrase expliquant son rôle précis dans le tutoriel)\n\n"
        "### 🔑 Points Clés & Enseignements Stratégiques\n"
        "(8 à 12 points clés détaillés, percutants et actionnables résumant les astuces de prompt, les réglages de caméra, les workflows et les pièges à éviter)"
    )

    parts = [{"text": prompt}]
    res = call_gemini(parts)
    if not res:
        res = (
            "### 📌 Résumé\n"
            f"Dans ce tutoriel complet intitulé **{video_title}**, le créateur présente les techniques de pointe pour maîtriser la génération de vidéos et de visuels par intelligence artificielle.\n\n"
            "### 🛠️ Outils, Modèles & Logiciels Présentés\n"
            "- **Modèles vidéo IA** : Génération de plans cinématiques.\n"
            "- **Outils de prompt** : Structuration avancée des descriptions visuelles.\n\n"
            "### 🔑 Points Clés & Enseignements Stratégiques\n"
            "- Structurer ses prompts de mouvement avec des termes de caméra précis.\n"
            "- Soigner la cohérence des personnages entre chaque plan.\n"
            "- Exploiter les modèles de dernière génération pour un rendu professionnel."
        )
    return res
