# Subtitler

Transcription et sous-titrage automatique de vidéos/audios, 100% en interne
(aucun fichier envoyé à un service externe).

Entrée : vidéo `.mp4` ou audio `.wav`. Sortie au choix : vidéo avec sous-titres
incrustés, vidéo + piste de sous-titres, fichier `.srt`, ou texte brut.

Le code applicatif se trouve dans [`j1_presentation_ia_cloud/projet/`](j1_presentation_ia_cloud/projet/).

## Installation

Prérequis : Python 3.11+, [ffmpeg](https://ffmpeg.org/) dans le `PATH`
(Windows : `winget install ffmpeg`), idéalement un GPU NVIDIA.

```bash
cd j1_presentation_ia_cloud/projet
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS : source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install -r ../../requirements.txt
```

Les commandes suivantes se lancent depuis `j1_presentation_ia_cloud/projet/`.

## Lancer l'application

```bash
python -m subtitler
```

- Interface : <http://127.0.0.1:8000>
- Admin (statistiques) : <http://127.0.0.1:8000/admin.html>
- Doc de l'API : <http://127.0.0.1:8000/docs>

`Ctrl+C` pour arrêter. Au premier lancement, le modèle Whisper est téléchargé
(~1,5 Go), puis mis en cache. Les traitements interrompus reprennent
automatiquement au redémarrage.

Configuration par variables d'environnement (valeurs par défaut) :

| Variable | Défaut | Rôle |
|---|---|---|
| `SUBTITLER_HOST` | `127.0.0.1` | Adresse d'écoute (`0.0.0.0` pour le réseau) |
| `SUBTITLER_PORT` | `8000` | Port |
| `SUBTITLER_DATA_DIR` | `data` | Fichiers envoyés, résultats, base SQLite |
| `SUBTITLER_DEFAULT_MODEL` | `whisper-medium.en` | Modèle par défaut |
| `SUBTITLER_DEVICE` | `cuda:0` | `cpu` pour forcer le CPU |
| `SUBTITLER_WORKERS` | `1` | Traitements simultanés (1 par GPU) |
| `SUBTITLER_MAX_UPLOAD_MB` | `500` | Taille maximale d'un fichier |

## API

| Route | Rôle |
|---|---|
| `POST /api/jobs` | Envoie un fichier (`file`, `output_kind`, `model` optionnel) |
| `GET /api/jobs/{id}` | État du traitement + texte transcrit |
| `GET /api/jobs/{id}/result` | Télécharge le résultat (`?inline=true` pour l'afficher) |
| `GET /api/jobs/{id}/subtitles.vtt` | Sous-titres WebVTT |
| `GET /api/jobs` | Historique des traitements |
| `GET /api/stats` | Statistiques d'usage |
| `GET /api/info` | Modèles et formats disponibles |
| `GET /api/health` | Sonde de santé |

`output_kind` : `video_embedded`, `video_track`, `subtitles` ou `text`.

```bash
curl -F file=@poc/input.mp4 -F output_kind=subtitles http://127.0.0.1:8000/api/jobs
```

## Architecture

```
subtitler/
├── api/            FastAPI + service de l'interface web
├── jobs/           modèle de données, SQLite, file d'attente
├── transcription/  modèles de transcription (interface + Whisper)
├── media.py        appels ffmpeg/ffprobe
├── subtitles.py    formats SRT, WebVTT, texte
└── web/            interface HTML/CSS/JS (sans build)
```

Un envoi est enregistré puis mis en file d'attente ; un worker extrait l'audio,
transcrit, puis génère le résultat. Avec un seul GPU, les envois simultanés
attendent leur tour plutôt que de saturer sa mémoire.

Ajouter un modèle de transcription :

```python
from subtitler.transcription import Segment, Transcriber, register

class MonModele(Transcriber):
    def transcribe(self, audio_path):
        return [Segment(start=0.0, end=1.5, text="Bonjour")]

register("mon-modele", lambda settings: MonModele())
```

Il apparaît alors dans l'interface et dans `/api/info`.

## Tests

```bash
pytest
```

Whisper est remplacé par un faux modèle : les tests tournent en quelques
secondes, sans GPU (ffmpeg requis).

## Performances mesurées

RTX 3060 Laptop (6 Go), `whisper-medium.en`, vidéo de 2 min 29 s : 41 s de
traitement une fois le modèle chargé (28 % de la durée de la vidéo).
