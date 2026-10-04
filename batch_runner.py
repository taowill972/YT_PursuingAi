import os
import sys
import json
import time
import subprocess
from pathlib import Path
from typing import Dict, Any, List

from config import (
    BASE_DIR,
    REPO_DIR,
    CATALOG_FILE,
    STATE_FILE,
    BATCH_SIZE
)
from pipeline import process_single_video
from git_manager import update_readme_index, commit_and_push_repo

def disable_cron_batch_job() -> bool:
    """Retire automatiquement la routine de crontab une fois toutes les vidéos traitées."""
    try:
        res = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=True)
        lines = res.stdout.splitlines()
        new_lines = [l for l in lines if "yt_pursuingai_batch" not in l and "run_cron.sh" not in l]
        if len(new_lines) != len(lines):
            new_cron = "\n".join(new_lines) + "\n"
            p = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE, text=True)
            p.communicate(new_cron)
            print("[BatchRunner] 🛑 Crontab 6h désactivé avec succès : la routine d'historique s'arrête définitivement.", flush=True)
            return True
        return False
    except Exception as e:
        print(f"[BatchRunner] Erreur lors de la désactivation du cron : {e}", flush=True)
        return False

def load_state() -> Dict[str, Any]:
    """Charge l'état d'avancement state.json."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[BatchRunner] Avertissement lecture state : {e}", flush=True)
    return {
        "processed_ids": [],
        "processed_videos": [],
        "last_run_timestamp": None,
        "completed_count": 0,
        "total_catalog_count": 0,
        "status": "idle"
    }

def save_state(state: Dict[str, Any]) -> None:
    """Sauvegarde atomique du state.json."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def main():
    print(f"\n===================================================================", flush=True)
    print(f"🚀 [BatchRunner] Lancement de la routine 6h (Lot de {BATCH_SIZE} vidéos)", flush=True)
    print(f"🕒 Horodatage : {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}", flush=True)
    print(f"===================================================================", flush=True)

    if not CATALOG_FILE.exists():
        print(f"[BatchRunner] ❌ Fichier catalogue introuvable : {CATALOG_FILE}", flush=True)
        sys.exit(1)

    with open(CATALOG_FILE, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    if isinstance(loaded, dict) and "videos" in loaded:
        catalog_entries = loaded["videos"]
    elif isinstance(loaded, dict) and "entries" in loaded:
        catalog_entries = loaded["entries"]
    elif isinstance(loaded, list):
        catalog_entries = loaded
    else:
        catalog_entries = list(loaded.values()) if isinstance(loaded, dict) else []

    total_catalog = len(catalog_entries)
    print(f"[BatchRunner] Catalogue global : {total_catalog} vidéos disponibles.", flush=True)

    state = load_state()
    state["total_catalog_count"] = total_catalog
    processed_ids_set = set(state.get("processed_ids", []))

    # Filtrer les vidéos non encore traitées dans l'ordre chronologique inverse (plus récentes d'abord)
    pending_videos = [v for v in catalog_entries if v.get("id") and v.get("id") not in processed_ids_set]
    print(f"[BatchRunner] Vidéos restantes à transcrire : {len(pending_videos)} / {total_catalog}", flush=True)

    # Si toutes les vidéos ont été traitées : arrêt définitif de la routine
    if len(pending_videos) == 0:
        print("\n🎉 [BatchRunner] TOUTES LES VIDÉOS DE LA CHAÎNE ONT ÉTÉ TRAITÉES !", flush=True)
        print("🛑 Arrêt définitif de l'automatisation. Seule l'écoute des nouveaux flux restera active.", flush=True)
        state["status"] = "ALL_VIDEOS_PROCESSED_AUTOMATION_COMPLETED"
        state["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        save_state(state)
        disable_cron_batch_job()
        sys.exit(0)

    # Sélection du lot de BATCH_SIZE (5 vidéos)
    batch = pending_videos[:BATCH_SIZE]
    print(f"[BatchRunner] Traitement du lot de {len(batch)} vidéos :", flush=True)
    for idx, v in enumerate(batch):
        print(f"  [{idx+1}/{len(batch)}] {v.get('id')} — {v.get('title')}", flush=True)

    state["status"] = "running"
    state["last_run_timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save_state(state)

    successful_in_batch = 0
    for idx, v in enumerate(batch):
        vid_id = v.get("id")
        title = v.get("title", "")
        print(f"\n--- Traitement [{idx+1}/{len(batch)}] : {vid_id} ---", flush=True)

        try:
            video_record = process_single_video(vid_id, catalog_title=title)
            state["processed_ids"].append(vid_id)
            state["processed_videos"].append(video_record)
            state["completed_count"] = len(state["processed_ids"])
            save_state(state)
            successful_in_batch += 1

            # Mise à jour continue du README.md et commit Git
            update_readme_index(state["processed_videos"], total_catalog_count=total_catalog)
            commit_and_push_repo(f"feat(transcription): YT-{vid_id} - {video_record.get('title', title)[:60]}")

        except Exception as e:
            print(f"[BatchRunner] ❌ Erreur sur la vidéo {vid_id} : {e}", flush=True)
            import traceback
            traceback.print_exc()
            time.sleep(5)

    remaining_after_batch = len(catalog_entries) - len(state["processed_ids"])
    print(f"\n===================================================================", flush=True)
    print(f"✨ [BatchRunner] Lot terminé : {successful_in_batch}/{len(batch)} vidéos traitées.", flush=True)
    print(f"📊 Bilan global : {len(state['processed_ids'])} / {total_catalog} vidéos ({remaining_after_batch} restantes).", flush=True)
    print(f"===================================================================", flush=True)

    if remaining_after_batch == 0:
        print("\n🎉 [BatchRunner] DERNIÈRE VIDÉO DE LA CHAÎNE ATTEINTE !", flush=True)
        print("🛑 Arrêt définitif de la routine 6h.", flush=True)
        state["status"] = "ALL_VIDEOS_PROCESSED_AUTOMATION_COMPLETED"
        state["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        save_state(state)
        disable_cron_batch_job()
    else:
        state["status"] = "waiting_next_cron"
        save_state(state)

if __name__ == "__main__":
    main()
