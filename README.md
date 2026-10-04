# 🎬 YT_PursuingAi — Transcriptions & Analyses Multimodales

> Base de connaissances et transcriptions intégrales mot pour mot en français (audio via `whisper-v3-large-turbo` et `gemini-3.5-flash-lite`, vision via `gemini-3.5-flash-lite`) avec captures d'écran clés et fiches HTML interactives de la chaîne YouTube **[Pursuing AI](https://www.youtube.com/@PursuingAi)** (`@PursuingAi`).

---

## 📊 Statistiques de l'Automatisation
- **Total de vidéos dans le catalogue** : `83`
- **Vidéos traitées et documentées** : `1 / 83` (`1.2%`)
- **Captures d'écran extraites** : `16`
- **Modèle Audio ASR** : `Whisper-v3-large-turbo` (routine VPS) & `Google Gemini 3.5 Flash-Lite` (prioritaire/rapide, 100% Verbatim Français)
- **Modèle Vision d'écran** : `Google Gemini 3.5 Flash-Lite` (Analyse d'interfaces, schémas, code, prompts et démos en direct)
- **Cadence de rattrapage (VPS)** : Lot de 7 vidéos toutes les 6 heures (des plus récentes aux plus anciennes)
- **Écoute passive permanente** : Détection instantanée 0 token (flux Atom XML YouTube RSS) des nouveaux uploads
- **Stockage Zéro Média VPS** : Les vidéos et audios temporaires sont purgés du VPS après génération, les fiches Markdown/HTML et captures sont archivées ici sur GitHub et synchronisées en local.

---

## 📑 Index des Transcriptions Disponibles

| Date | Titre & Fiche Markdown | Fiche Web Interactive | Durée | Captures | Lien YouTube | ID Vidéo |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| 2026-09-22 | [Jev est BIEN plus puissant que nous le pensions (Jev Is WAY More Powerful Than W](2026-09-22_YT-I34qxJjyms0_Jev est BIEN plus puissant que nous le pensions (Jev Is WAY More Powerful Than W_by-gemini-3.5-flash-lite.md) | [🌐 Consulter la fiche interactive](2026-09-22_YT-I34qxJjyms0_Jev est BIEN plus puissant que nous le pensions (Jev Is WAY More Powerful Than W_by-gemini-3.5-flash-lite.html) | 08m 11s | `16 images` | [Voir sur YouTube](https://www.youtube.com/watch?v=I34qxJjyms0) | `I34qxJjyms0` |

---

## 🛠️ Architecture du Système Déployé

```
├── catalog.json              # Catalogue exhaustif des 83 vidéos de la chaîne @PursuingAi
├── state.json                # Suivi de progression (vidéos traitées, en attente, erreurs)
├── README.md                 # Sommaire dynamique et index navigable
├── screenshots/              # Captures d'écran HD horodatées des démonstrations d'outils
│   └── I34qxJjyms0_shot_*.jpg
├── *.md                      # Fiches Markdown complètes structurées (Synthèse, Outils, Chronologie)
└── *.html                    # Interfaces web interactives sombres, responsives avec Lightbox
```

*Généré automatiquement par l'agent de veille multimodale Antigravity.*
