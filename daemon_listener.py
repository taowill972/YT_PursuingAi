import os
import sys
import time
import json
import signal
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Any, Optional

from config import (
    BASE_DIR,
    CATALOG_FILE,
    STATE_FILE,
    RSS_FEED_URL,
    CHANNEL_ID,
    CHANNEL_NAME,
    PROXY,
    PLAYER_CLIENT
)
from pipeline import process_single_video
from git_manager import update_readme_index, commit_and_push_repo

POLL_INTERVAL_SECONDS = 900  # 15 minutes entre chaque interrogation du flux RSS

running = True

def handle_signal(sig, frame):
    global running
    print(f"\n[Listener] Signal {sig} reçu, arrêt propre du démon d'écoute...", flush=True)
    running = False

signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)

def load_state() -> Dict[str, Any]:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"processed_ids": [], "processed_videos": [], "completed_count": 0}

def save_state(state: Dict[str, Any]) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def fetch_rss_videos() -> List[Dict[str, str]]:
    """
    Récupère instantanément les dernières vidéos publiées via le flux Atom XML YouTube officiel.
    Consommation : 0 TOKEN LLM, 0 QUOTA API, 100% GRATUIT & IMMÉDIAT.
    """
    req = urllib.request.Request(
        RSS_FEED_URL,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            xml_data = resp.read()
    except Exception as e:
        print(f"[Listener] Avertissement flux RSS ({e}), bascule sur fallback yt-dlp...", flush=True)
        return fetch_ytdlp_latest()

    videos = []
    try:
        root = ET.fromstring(xml_data)
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "yt": "http://www.youtube.com/xml/schemas/2015"
        }
        for entry in root.findall("atom:entry", ns):
            vid_id_elem = entry.find("yt:videoId", ns)
            title_elem = entry.find("atom:title", ns)
            pub_elem = entry.find("atom:published", ns)

            if vid_id_elem is not None and vid_id_elem.text:
                vid_id = vid_id_elem.text.strip()
                title = title_elem.text.strip() if title_elem is not None else ""
                published = pub_elem.text.strip() if pub_elem is not None else ""
                videos.append({
                    "id": vid_id,
                    "title": title,
                    "published": published
                })
    except Exception as e:
        print(f"[Listener] Erreur parsing XML Atom : {e}", flush=True)

    return videos

def fetch_ytdlp_latest() -> List[Dict[str, str]]:
    cmd = [
        "yt-dlp",
        "--proxy", PROXY,
        "--extractor-args", f"youtube:player_client={PLAYER_CLIENT}",
        "--flat-playlist",
        "--playlist-end", "5",
        "--dump-json",
        f"https://www.youtube.com/@PursuingAi/videos"
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        entries = []
        for line in res.stdout.strip().splitlines():
            if not line.strip(): continue
            d = json.loads(line)
            entries.append({"id": d.get("id"), "title": d.get("title", "")})
        return entries
    except Exception as e:
        print(f"[Listener] Erreur fallback yt-dlp : {e}", flush=True)
        return []

def listen_loop():
    print(f"\n===================================================================", flush=True)
    print(f"👂 [Listener] Démarrage de l'Écoute Passive YouTube (0 Token LLM)", flush=True)
    print(f"📺 Chaîne surveillée : {CHANNEL_NAME} ({CHANNEL_ID})", flush=True)
    print(f"📡 Flux RSS Atom : {RSS_FEED_URL}", flush=True)
    print(f"⏱️ Intervalle de vérification : toutes les {POLL_INTERVAL_SECONDS // 60} minutes", flush=True)
    print(f"===================================================================\n", flush=True)

    initial_backlog_ids = set()
    if CATALOG_FILE.exists():
        with open(CATALOG_FILE, "r", encoding="utf-8") as f:
            cat_data = json.load(f)
            entries = cat_data if isinstance(cat_data, list) else cat_data.get("videos", [])
            initial_backlog_ids = {v.get("id") for v in entries if isinstance(v, dict) and v.get("id")}
    print(f"[Listener] {len(initial_backlog_ids)} vidéos répertoriées dans le backlog initial.", flush=True)

    while running:
        t_now = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        print(f"[{t_now}] [Listener] Vérification des nouvelles publications...", flush=True)

        try:
            latest_videos = fetch_rss_videos()
            state = load_state()
            processed_ids = set(state.get("processed_ids", []))

            catalog_videos = []
            if CATALOG_FILE.exists():
                with open(CATALOG_FILE, "r", encoding="utf-8") as f:
                    cat_data = json.load(f)
                    catalog_videos = cat_data if isinstance(cat_data, list) else cat_data.get("videos", [])
            catalog_ids = {v.get("id") for v in catalog_videos if isinstance(v, dict) and v.get("id")}

            for v in reversed(latest_videos):
                vid_id = v.get("id")
                title = v.get("title", "")
                if not vid_id:
                    continue

                is_backlog_video = vid_id in initial_backlog_ids
                if not is_backlog_video and vid_id not in processed_ids:
                    print(f"\n🚨 [Listener] NOUVELLE VIDÉO INÉDITE DÉTECTÉE SUR LA CHAÎNE !", flush=True)
                    print(f"     ID    : {vid_id}", flush=True)
                    print(f"     Titre : {title}", flush=True)

                    if vid_id not in catalog_ids:
                        catalog_videos.insert(0, {"id": vid_id, "title": title, "duration": None})
                        with open(CATALOG_FILE, "w", encoding="utf-8") as f:
                            json.dump(catalog_videos, f, ensure_ascii=False, indent=2)
                        catalog_ids.add(vid_id)

                    print(f"[Listener] 🚀 Lancement automatique de la transcription/description...", flush=True)
                    try:
                        record = process_single_video(vid_id, catalog_title=title)
                        state["processed_ids"].append(vid_id)
                        state["processed_videos"].insert(0, record)
                        state["completed_count"] = len(state["processed_ids"])
                        save_state(state)

                        update_readme_index(state["processed_videos"], total_catalog_count=len(catalog_videos))
                        commit_and_push_repo(f"feat(listener): NOUVELLE VIDÉO YT-{vid_id} - {record.get('title', title)[:60]}")
                        print(f"[Listener] ✅ Nouvelle vidéo traitée et poussée vers GitHub avec succès !\n", flush=True)
                    except Exception as e:
                        print(f"[Listener] ❌ Erreur traitement vidéo {vid_id} : {e}", flush=True)

        except Exception as e:
            print(f"[Listener] Exception générale dans la boucle d'écoute : {e}", flush=True)

        for _ in range(POLL_INTERVAL_SECONDS):
            if not running:
                break
            time.sleep(1)

    print("[Listener] Démon d'écoute arrêté proprement.", flush=True)

if __name__ == "__main__":
    listen_loop()
