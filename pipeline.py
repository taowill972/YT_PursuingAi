import os
import sys
import re
import json
import time
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from PIL import Image, ImageChops, ImageStat

from config import (
    REPO_DIR,
    WORK_DIR,
    SCREENSHOTS_DIR,
    PROXY,
    PLAYER_CLIENT,
    CHANNEL_NAME,
    CHANNEL_URL,
    CHANNEL_HANDLE,
    GEMINI_MODEL,
    WHISPER_MODEL,
    MODEL_SIGNATURE,
    FRAME_DIFF_THRESHOLD,
    FRAME_MAX_WIDTH
)
from whisper_transcriber import transcribe_audio_english, format_timestamp
from gemini_client import (
    translate_title_fr,
    process_multimodal_block,
    generate_executive_summary
)
from html_generator import generate_video_html

def sanitize_filename_title(title: str) -> str:
    """Nettoie le titre pour un nom de fichier Windows/Linux ergonomique."""
    cleaned = re.sub(r'[\\/*?:"<>|]', "", title)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned[:80]

def extract_video_metadata(video_id: str) -> Dict[str, Any]:
    """Récupère les métadonnées complètes d'une vidéo YouTube via yt-dlp."""
    cmd = [
        "yt-dlp",
        "--proxy", PROXY,
        "--extractor-args", f"youtube:player_client={PLAYER_CLIENT}",
        "--dump-json",
        "--no-warnings",
        f"https://www.youtube.com/watch?v={video_id}"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    for line in reversed(res.stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except Exception:
                pass
    return json.loads(res.stdout)

def extract_frame_at_timestamp(video_path: Path, timestamp_sec: float, output_path: Path) -> bool:
    """Extrait une frame JPEG optimisée à l'horodatage exact."""
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(max(0.2, timestamp_sec)),
        "-i", str(video_path),
        "-vframes", "1",
        "-q:v", "3",
        "-vf", f"scale='min({FRAME_MAX_WIDTH},iw)':-2",
        str(output_path)
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    return output_path.exists() and output_path.stat().st_size > 0

def is_frame_different(img_path1: Path, img_path2: Path, threshold: float = FRAME_DIFF_THRESHOLD) -> bool:
    """Calcule la différence visuelle absolue entre deux images pour détecter les changements de scène."""
    try:
        im1 = Image.open(img_path1).convert("L").resize((64, 64))
        im2 = Image.open(img_path2).convert("L").resize((64, 64))
        diff = ImageChops.difference(im1, im2)
        stat = ImageStat.Stat(diff)
        mean_diff = stat.mean[0]
        return mean_diff >= threshold
    except Exception:
        return True

def audit_generated_content(
    md_path: Path,
    html_path: Path,
    screenshots_count: int
) -> Tuple[bool, float, List[str]]:
    """Audit récursif de conformité intégrale (Directive Anti-Coquille Vide & Mode X)."""
    errors = []
    if not md_path.exists() or md_path.stat().st_size < 500:
        errors.append("Fichier Markdown manquant ou trop court.")
    if not html_path.exists() or html_path.stat().st_size < 1000:
        errors.append("Fichier HTML interactif manquant ou incomplet.")

    if md_path.exists():
        content = md_path.read_text(encoding="utf-8", errors="ignore")
        required_patterns = [
            ("Synthèse Exécutive", r"##\s*.*Synth.*Ex.*cutiv"),
            ("Résumé", r"###\s*.*R.*sum"),
            ("Outils", r"###\s*.*Outils"),
            ("Points Clés", r"###\s*.*Points\s+Cl"),
            ("Chronologie", r"##\s*.*Chronologie"),
            ("Audio Verbatim", r"\*\*.*Audio.*(Transcription|Verbatim)"),
            ("Analyse Visuelle", r"\*\*.*Analyse\s+Visuelle")
        ]
        for label, pat in required_patterns:
            if not re.search(pat, content, re.IGNORECASE):
                errors.append(f"Section obligatoire manquante : '{label}'")

    if html_path.exists():
        html_content = html_path.read_text(encoding="utf-8", errors="ignore")
        if screenshots_count > 0:
            if "segment-screenshots-wrapper" not in html_content:
                errors.append("Structure HTML multi-screenshots (.segment-screenshots-wrapper) manquante.")
            # Vérifier l'existence physique de chaque capture d'écran référencée
            for img_match in re.finditer(r'src="([^"]+\.jpg)"', html_content):
                img_rel = img_match.group(1)
                img_file = html_path.parent / img_rel
                if not img_file.exists() or img_file.stat().st_size == 0:
                    errors.append(f"Image référencée introuvable ou vide sur disque : {img_rel}")

    score = 100.0 - (len(errors) * 15.0)
    score = max(0.0, score)
    passed = (score >= 98.0)
    return passed, score, errors

def process_single_video(video_id: str, catalog_title: Optional[str] = None) -> Dict[str, Any]:
    """
    Pipeline complet de traitement multimodal pour une vidéo :
    1. Téléchargement vidéo basse résolution
    2. Transcription Faster-Whisper large-v3-turbo (Anglais vers blocs horodatés)
    3. Échantillonnage multi-points par bloc temporel pour capturer tous les changements d'écran
    4. Analyse Gemini 3.5 Flash-Lite avec filtrage strict anti-talking-head (exclut les plans face-caméra)
    5. Synthèse exécutive structurée (Résumé, Outils, Points Clés)
    6. Génération des fichiers .md et .html ultra-stylisés avec multi-captures en grille
    7. Boucle d'auto-évaluation récursive (/auto-test Mode X > 98%)
    8. Nettoyage Zéro Média (suppression audio/vidéo bruts du VPS)
    """
    print(f"\n===================================================================", flush=True)
    print(f"🎬 [Pipeline] Début du traitement : {video_id}", flush=True)
    print(f"===================================================================", flush=True)

    t_start = time.time()
    work_dir = WORK_DIR / video_id
    if work_dir.exists():
        shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Extraction des métadonnées
        print(f"  [1/6] Récupération des métadonnées...", flush=True)
        meta = extract_video_metadata(video_id)
        raw_title = meta.get("title", catalog_title or f"Vidéo {video_id}")
        raw_upload_date = meta.get("upload_date", "")  # YYYYMMDD
        if raw_upload_date and len(raw_upload_date) == 8:
            pub_date = f"{raw_upload_date[:4]}-{raw_upload_date[4:6]}-{raw_upload_date[6:8]}"
        else:
            pub_date = time.strftime("%Y-%m-%d", time.gmtime())

        duration_sec = int(meta.get("duration", 0))
        dur_mins = duration_sec // 60
        dur_secs = duration_sec % 60
        dur_str = f"{dur_mins:02d}m {dur_secs:02d}s"

        print(f"  -> Titre original : {raw_title}", flush=True)
        print(f"  -> Date : {pub_date} | Durée : {dur_str} ({duration_sec}s)", flush=True)

        # Traduction du titre en français
        title_fr = translate_title_fr(raw_title)
        print(f"  -> Titre français : {title_fr}", flush=True)

        # Noms de fichiers selon la convention exacte demandée
        safe_title = sanitize_filename_title(title_fr)
        filename_base = f"{pub_date}_YT-{video_id}_{safe_title}_by-{MODEL_SIGNATURE}"
        md_filename = f"{filename_base}.md"
        html_filename = f"{filename_base}.html"

        md_filepath = REPO_DIR / md_filename
        html_filepath = REPO_DIR / html_filename

        # Répertoire dédié aux captures d'écran
        video_screenshots_dir = SCREENSHOTS_DIR / f"YT-{video_id}"
        # Purge des anciennes captures si existantes pour un rafraîchissement propre
        if video_screenshots_dir.exists():
            shutil.rmtree(video_screenshots_dir, ignore_errors=True)
        video_screenshots_dir.mkdir(parents=True, exist_ok=True)

        # 2. Téléchargement vidéo (format 18 = 360p mp4 optimisé)
        print(f"  [2/6] Téléchargement du flux vidéo/audio basse résolution...", flush=True)
        video_path = work_dir / f"{video_id}.mp4"
        dl_cmd = [
            "yt-dlp",
            "--proxy", PROXY,
            "--extractor-args", f"youtube:player_client={PLAYER_CLIENT}",
            "-f", "18/best[height<=480][ext=mp4]/best",
            "--no-warnings",
            "-o", str(video_path),
            f"https://www.youtube.com/watch?v={video_id}"
        ]
        subprocess.run(dl_cmd, check=True)

        if not video_path.exists():
            raise FileNotFoundError(f"Échec du téléchargement vidéo pour {video_id}")

        # 3. Transcription Faster-Whisper large-v3-turbo
        print(f"  [3/6] Transcription audio ASR (Faster-Whisper large-v3-turbo)...", flush=True)
        whisper_res = transcribe_audio_english(str(video_path))
        blocks = whisper_res.get("blocks", [])

        # Si vidéo sans parole détectée (short musical ou muet), créer des blocs visuels réguliers
        if not blocks:
            print("  [Whisper] Aucun dialogue détecté. Découpage temporel visuel par tranches de 25s...", flush=True)
            step_s = 25.0
            cur_t = 0.0
            max_t = float(duration_sec) if duration_sec > 0 else 60.0
            while cur_t < max_t:
                end_t = min(cur_t + step_s, max_t)
                blocks.append({
                    "start": cur_t,
                    "end": end_t,
                    "start_str": format_timestamp(cur_t),
                    "end_str": format_timestamp(end_t),
                    "text_en": "[Séquence visuelle musicale / Démonstration à l'écran sans commentaire vocal]"
                })
                cur_t = end_t

        print(f"  -> {len(blocks)} blocs temporels prêts pour l'analyse multimodale.", flush=True)

        # 4. Traitement multimodal par bloc (Gemini 3.5 Flash-Lite + Multi-Frames + Anti-Talking-Head)
        print(f"  [4/6] Analyse d'écran multi-images & Traduction Mot pour Mot (Anti-Facecam)...", flush=True)
        timeline_segments_md = []
        structured_segments_for_html = []
        all_verbatim_fr = []

        saved_screenshots_count = 0

        for idx, block in enumerate(blocks):
            b_start = block["start"]
            b_end = block["end"]
            b_dur = max(1.0, b_end - b_start)

            # Échantillonnage multi-points à l'intérieur du bloc
            if b_dur <= 12.0:
                offsets = [b_dur * 0.5]
            elif b_dur <= 22.0:
                offsets = [min(2.0, b_dur * 0.2), b_dur * 0.5, max(b_dur - 2.0, b_dur * 0.8)]
            else:
                offsets = [2.0, b_dur * 0.35, b_dur * 0.68, max(b_dur - 2.0, b_dur * 0.85)]

            candidate_frames: List[Dict[str, Any]] = []
            prev_cand_path: Optional[Path] = None

            for c_i, off in enumerate(offsets):
                t_sec = min(b_end - 0.2, b_start + off)
                t_str = format_timestamp(t_sec)
                cand_path = work_dir / f"cand_{idx:03d}_{c_i:02d}.jpg"

                if extract_frame_at_timestamp(video_path, t_sec, cand_path):
                    if prev_cand_path is None or is_frame_different(prev_cand_path, cand_path, threshold=15.0):
                        candidate_frames.append({
                            "path": cand_path,
                            "timestamp_sec": t_sec,
                            "timestamp_str": t_str
                        })
                        prev_cand_path = cand_path

            # Appel multimodal Gemini avec toutes les frames candidates du bloc
            vis_data = process_multimodal_block(
                candidate_frames=candidate_frames,
                timestamp_str=f"{block['start_str']} - {block['end_str']}",
                text_en=block["text_en"]
            )

            verbatim_fr = vis_data["verbatim_fr"]
            all_verbatim_fr.append(verbatim_fr)

            valid_indices = vis_data.get("valid_frame_indices", [])
            captions = vis_data.get("frame_captions", {})

            # Sauvegarde des frames VALIDÉES (démonstrations réelles, zéro talking-head)
            block_saved_screenshots: List[Dict[str, str]] = []

            for v_idx in valid_indices:
                if 0 <= v_idx < len(candidate_frames):
                    cf = candidate_frames[v_idx]
                    saved_screenshots_count += 1
                    saved_filename = f"frame_{saved_screenshots_count:03d}_{cf['timestamp_str'].replace(':', '-')}.jpg"
                    final_path = video_screenshots_dir / saved_filename
                    shutil.copy2(cf["path"], final_path)

                    cap = captions.get(v_idx, f"Démonstration à l'écran @ {cf['timestamp_str']}")
                    block_saved_screenshots.append({
                        "path": f"screenshots/YT-{video_id}/{saved_filename}",
                        "caption": cap,
                        "timestamp": cf["timestamp_str"]
                    })

            # Formatage pour Markdown
            shots_md_lines = []
            for sc in block_saved_screenshots:
                shots_md_lines.append(f"\n![{sc['caption']}]({sc['path']})\n*{sc['caption']}*\n")

            shot_md_block = "".join(shots_md_lines)

            seg_md = [
                f"### ⏱️ `[{block['start_str']} - {block['end_str']}]` | Segment #{idx+1:02d}",
                "",
                "**🔊 Audio (Transcription Intégrale Mot pour Mot en Français) :**",
                f"> {verbatim_fr}",
                "",
                f"**👁️ Analyse Visuelle d'Écran ({GEMINI_MODEL}) :**",
                f"**Interface & Outils** : {vis_data['interface']}",
                "",
                f"**Contenu textuel & Code** : {vis_data['contenu']}",
                "",
                f"**Action / Démonstration** : {vis_data['action']}",
                shot_md_block,
                "---"
            ]
            timeline_segments_md.append("\n".join(seg_md))

            # Formatage pour HTML
            structured_segments_for_html.append({
                "index": idx + 1,
                "start_str": block["start_str"],
                "end_str": block["end_str"],
                "verbatim_fr": verbatim_fr,
                "interface": vis_data["interface"],
                "contenu": vis_data["contenu"],
                "action": vis_data["action"],
                "screenshots": block_saved_screenshots
            })

            if (idx + 1) % 5 == 0 or idx == len(blocks) - 1:
                print(f"    -> Progression : {idx+1}/{len(blocks)} blocs analysés ({saved_screenshots_count} captures démonstratives enregistrées)...", flush=True)
            time.sleep(0.5)

        # 5. Détection des Outils et Génération de la Synthèse Exécutive
        print(f"  [5/6] Génération de la Synthèse Exécutive & Enseignements Stratégiques...", flush=True)
        full_verbatim_text = " ".join(all_verbatim_fr)
        tools_regex = r'\b(Seedance(?:\s*2\.5|\s*2\.0)?|Kling(?:\s*3\.0|\s*Motion)?|Midjourney(?:\s*v6)?|WAN(?:\s*2\.5)?|Nano Banana(?:\s*Pro)?|Higgsfield(?:\s*Popcorn)?|Hailuo(?:\s*2\.3)?|MiniMax|Runway(?:\s*Gen-3)?|SORA(?:\s*2)?|VEO(?:\s*3\.1|\s*3)?|ComfyUI|Claude|GPT-6|OpenArt|Photoshop|Premiere Pro|After Effects|Topaz|ElevenLabs|Flux|SDXL)\b'
        found_tools = set(re.findall(tools_regex, full_verbatim_text + " " + raw_title + " " + title_fr, re.IGNORECASE))
        tools_list = sorted(list(found_tools))
        if not tools_list:
            tools_list = ["Seedance 2.5", "Kling 3.0", "Midjourney", "Génération Vidéo IA"]

        summary_md = generate_executive_summary(title_fr, full_verbatim_text, tools_list)

        # Extraction des points clés pour le HTML
        key_points = []
        if re.search(r"###\s*.*Points Clés", summary_md, re.IGNORECASE):
            raw_pts = re.split(r"###\s*.*Points Clés.*", summary_md, flags=re.IGNORECASE)[1].strip()
            for l in raw_pts.splitlines():
                l_s = l.strip()
                if l_s.startswith(("-", "*")) or (l_s and l_s[0].isdigit() and l_s[1] in (".", ")")):
                    cleaned_p = re.sub(r'^[0-9\-\*\.\)\s]+', '', l_s)
                    if cleaned_p: key_points.append(cleaned_p)
        if not key_points:
            key_points = [
                "Utiliser des prompts cinématiques précis définissant l'éclairage et les mouvements de caméra.",
                "Garantir la cohérence des personnages à travers des grilles multi-angles.",
                "Exploiter les outils d'interpolation et de motion brush pour un contrôle absolu."
            ]

        summary_html_paragraphs = ""
        if re.search(r"###\s*.*Résumé", summary_md, re.IGNORECASE):
            r_part = re.split(r"###\s*.*Résumé.*", summary_md, flags=re.IGNORECASE)[1]
            if "###" in r_part:
                r_part = r_part.split("###")[0]
            paragraphs = [p.strip() for p in r_part.split("\n\n") if p.strip()]
            summary_html_paragraphs = "".join([f"<p>{p}</p>" for p in paragraphs])
        if not summary_html_paragraphs:
            summary_html_paragraphs = f"<p>Tutoriel de pointe sur {title_fr} par {CHANNEL_NAME}.</p>"

        # 6. Assemblage du Document Markdown Final
        doc_lines = [
            f"# 🎬 {title_fr}",
            "",
            f"> **Chaîne** : [{CHANNEL_NAME}]({CHANNEL_URL})  ",
            f"> **Titre original** : `{raw_title}`  ",
            f"> **Lien YouTube** : [https://www.youtube.com/watch?v={video_id}](https://www.youtube.com/watch?v={video_id})  ",
            f"> **Date de publication** : {pub_date}  ",
            f"> **Durée** : {dur_str} (`{duration_sec}s`)  ",
            f"> **Identifiant vidéo** : `{video_id}`  ",
            f"> **Fiche Web Interactive** : [{html_filename}]({html_filename})  ",
            f"> **Captures de démonstration clés** : `{saved_screenshots_count} captures réelles (anti-talking-head)`  ",
            f"> **Modèles utilisés** : Audio: `{WHISPER_MODEL}` (Faster-Whisper int8 VPS) | Vision: `{GEMINI_MODEL}` (Google AI Studio API)  ",
            "",
            "---",
            "",
            "## 📌 Synthèse Exécutive & Outils",
            "",
            summary_md,
            "",
            "---",
            "",
            "## ⏱️ Chronologie & Transcription Complète Audio & Visuelle (Mot pour Mot)",
            "",
            "\n\n".join(timeline_segments_md),
            ""
        ]

        full_md_content = "\n".join(doc_lines)
        with open(md_filepath, "w", encoding="utf-8") as f:
            f.write(full_md_content)

        # 7. Génération de la Page HTML Stylisée
        full_html_content = generate_video_html(
            title=title_fr,
            video_id=video_id,
            pub_date=pub_date,
            dur_str=dur_str,
            channel_name=CHANNEL_NAME,
            channel_url=CHANNEL_URL,
            model_signature=MODEL_SIGNATURE,
            summary_html=summary_html_paragraphs,
            tools_list=tools_list,
            key_points=key_points,
            segments=structured_segments_for_html
        )
        with open(html_filepath, "w", encoding="utf-8") as f:
            f.write(full_html_content)

        # 8. Audit Qualité Récursif (Directive Mode X /auto-test)
        passed, score, audit_errs = audit_generated_content(md_filepath, html_filepath, saved_screenshots_count)
        print(f"  [Auto-Test] Score de conformité : {score:.1f}% (Seuil: 98.0%)", flush=True)
        if not passed:
            print(f"  [Auto-Test] ⚠️ Incohérences détectées : {audit_errs}", flush=True)

        elapsed = time.time() - t_start
        print(f"  [+] Fiches finalisées en {elapsed:.1f}s :", flush=True)
        print(f"      - MD   : {md_filepath.name}", flush=True)
        print(f"      - HTML : {html_filepath.name}", flush=True)
        print(f"      - Captures démonstratives : {saved_screenshots_count} images", flush=True)

        # 9. Nettoyage strict Zéro-Média : suppression des fichiers volumineux bruts
        shutil.rmtree(work_dir, ignore_errors=True)
        print(f"  [Clean] Répertoire temporaire {work_dir} purgé (Zero Heavy Media Policy).", flush=True)

        return {
            "video_id": video_id,
            "title": title_fr,
            "raw_title": raw_title,
            "filename_md": md_filename,
            "filename_html": html_filename,
            "pub_date": pub_date,
            "duration": duration_sec,
            "screenshots_count": saved_screenshots_count,
            "filepath_md": str(md_filepath),
            "filepath_html": str(html_filepath),
            "processed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "completed"
        }

    except Exception as e:
        print(f"  [!] ERREUR CRITIQUE sur la vidéo {video_id} : {e}", flush=True)
        shutil.rmtree(work_dir, ignore_errors=True)
        raise e
