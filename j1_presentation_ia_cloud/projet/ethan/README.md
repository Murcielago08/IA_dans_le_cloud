# Subtitler

Application de transcription et de sous-titrage automatique, hébergée en interne :
aucune vidéo n'est envoyée à un service externe.

Elle prend en entrée une vidéo `.mp4` ou un audio `.wav` et renvoie, au choix :

| Fichier envoyé | Vidéo sous-titres incrustés | Vidéo + piste de sous-titres | Sous-titres `.srt` | Texte seul |
|----------------|:---:|:---:|:---:|:---:|
| Vidéo `.mp4`   | ✓ | ✓ | ✓ | ✓ |
| Audio `.wav`   |   |   | ✓ | ✓ |

## Installation

Prérequis : Python 3.11+, [ffmpeg](https://ffmpeg.org/) dans le `PATH`
(Windows : `winget install ffmpeg`), et idéalement un GPU NVIDIA.

```bash
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS : source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt
```

## Lancement et arrêt

```bash
python -m subtitler
```

- Interface utilisateur : <http://127.0.0.1:8000>
- Administration (statistiques) : <http://127.0.0.1:8000/admin.html>
- Documentation interactive de l'API : <http://127.0.0.1:8000/docs>

Arrêt : `Ctrl+C`. Les traitements en attente ou interrompus (arrêt, crash) sont
repris automatiquement au démarrage suivant.

Au premier lancement, le modèle est téléchargé depuis Hugging Face (~1,5 Go pour
`whisper-medium.en`), puis il est gardé en cache.

### Configuration

Par variables d'environnement :

| Variable | Défaut | Rôle |
|---|---|---|
| `SUBTITLER_HOST` | `127.0.0.1` | Adresse d'écoute (`0.0.0.0` pour le réseau) |
| `SUBTITLER_PORT` | `8000` | Port |
| `SUBTITLER_DATA_DIR` | `data` | Fichiers envoyés, résultats et base SQLite |
| `SUBTITLER_DEFAULT_MODEL` | `whisper-medium.en` | Modèle par défaut |
| `SUBTITLER_DEVICE` | `cuda:0` | `cpu` pour forcer le CPU |
| `SUBTITLER_WORKERS` | `1` | Traitements simultanés (1 par GPU) |
| `SUBTITLER_MAX_UPLOAD_MB` | `500` | Taille maximale d'un fichier |

## API

| Méthode | Route | Rôle |
|---|---|---|
| `POST` | `/api/jobs` | Envoie un fichier (`file`, `output_kind`, `model` optionnel), renvoie le job (202) |
| `GET` | `/api/jobs/{id}` | État du traitement et texte transcrit |
| `GET` | `/api/jobs/{id}/result` | Télécharge le résultat (`?inline=true` pour l'afficher) |
| `GET` | `/api/jobs/{id}/subtitles.vtt` | Sous-titres WebVTT (aperçu dans le navigateur) |
| `GET` | `/api/jobs` | Derniers traitements, avec le contenu des réponses |
| `GET` | `/api/stats` | Statistiques d'usage |
| `GET` | `/api/info` | Modèles et types de résultats disponibles |
| `GET` | `/api/health` | Sonde de santé |

`output_kind` vaut `video_embedded`, `video_track`, `subtitles` ou `text`.

```bash
curl -F file=@poc/input.mp4 -F output_kind=subtitles http://127.0.0.1:8000/api/jobs
```

## Architecture

```
subtitler/
├── api/            API FastAPI + service de l'interface web
├── jobs/           modèle de données, persistance SQLite, file d'attente
├── transcription/  modèles de transcription (interface + Whisper + catalogue)
├── media.py        appels ffmpeg/ffprobe
├── subtitles.py    formats SRT, WebVTT, texte
└── web/            interface HTML/CSS/JS (sans build)
```

Un envoi est enregistré en base puis placé dans une file d'attente. Un worker le
traite : extraction de l'audio, transcription, génération du résultat. Avec un seul
GPU, les demandes simultanées attendent leur tour au lieu de saturer sa mémoire.

### Ajouter un modèle de transcription

```python
from subtitler.transcription import Segment, Transcriber, register

class MonModele(Transcriber):
    def transcribe(self, audio_path):
        return [Segment(start=0.0, end=1.5, text="Bonjour")]

register("mon-modele", lambda settings: MonModele())
```

Le modèle apparaît alors dans l'interface et dans `/api/info`.

## Tests

```bash
pytest
```

Les tests remplacent Whisper par un faux modèle : ils tournent en quelques
secondes, sans GPU. Seul ffmpeg est requis.

## Performances mesurées

RTX 3060 Laptop (6 Go), `whisper-medium.en`, vidéo d'exemple de 2 min 29 s :
41 s de traitement une fois le modèle chargé, soit 28 % de la durée de la vidéo.
