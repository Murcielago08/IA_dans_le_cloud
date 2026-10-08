# Subtitler

Transcription et sous-titrage automatique de vidéos/audios, 100% en interne
(aucun fichier envoyé à un service externe).

Entrée : vidéo `.mp4` ou audio `.wav`. Sortie au choix : vidéo avec sous-titres
incrustés, vidéo + piste de sous-titres, fichier `.srt`, ou texte brut.

Le code applicatif se trouve dans [`Projet/`](Projet/).

## Avancement par rapport au cahier des charges

Référence : [`Projet Fil rouge.pdf`](Projet/Projet%20Fil%20rouge.pdf).
Avancement global estimé : **~60 %** — le pipeline applicatif (API, traitement,
interface, stats) est solide ; le volet *industrialisation cloud* (déploiement,
charge, coût d'infra) reste largement à faire.

### Besoins fonctionnels obligatoires — Administrateur (~95 %)

| Besoin | Avancement | Détail |
|---|---|---|
| Installer via la documentation | 100 % | Section [Installation](#installation) ci-dessous |
| Arrêter la solution | 100 % | `Ctrl+C` |
| Relancer après arrêt/crash | 90 % | Les traitements interrompus reprennent automatiquement au redémarrage ; pas de superviseur (systemd/Docker restart) pour un redémarrage *automatique* après crash sans action humaine |
| Statistiques d'usage (temps moyen, nb inférences par type, contenu des réponses, non terminés/échoués par type) | 100 % | `GET /api/stats` + page `admin.html` : tous les indicateurs demandés sont présents |

### Besoins fonctionnels obligatoires — Utilisateur / Data scientist (~80 %)

| Besoin | Avancement | Détail |
|---|---|---|
| Upload vidéo `.mp4` | 100 % | |
| Upload audio `.wav` | 100 % | |
| Choix du type de résultat selon le tableau du besoin | 100 % | Règles appliquées strictement (`ALLOWED_OUTPUTS`) |
| Lancer le traitement puis télécharger le résultat | 100 % | |
| Ajouter un nouveau modèle de transcription | 100 % | Mécanisme d'extension `register()` documenté |
| Faire évoluer la transcription avec l'identification du speaker | 0 % | Non implémenté — seul le point d'extension existe |

### Besoins fonctionnels facultatifs (~35 %)

| Besoin | Avancement | Détail |
|---|---|---|
| Consulter le résultat sur l'interface sans le télécharger | 100 % | Bouton « Aperçu » |
| Interfacer la solution au service de traduction | 0 % | Non traité |
| Autre besoin jugé pertinent | — | Non applicable / non défini avec le client |

### Performance & infrastructure (~20 %)

| Besoin | Avancement | Détail |
|---|---|---|
| Traitement plus rapide que la durée de l'échantillon | 70 % | Démontré sur un seul cas mesuré (voir [Performances mesurées](#performances-mesurées)), pas sur l'ensemble des modèles/formats |
| Tenue de la performance jusqu'à 10 utilisateurs en parallèle | 5 % | `SUBTITLER_WORKERS=1` par défaut : les requêtes sont traitées **en série**, pas en parallèle. Aucun test de charge réalisé |
| Estimation de l'infrastructure nécessaire | 0 % | Aucun document de dimensionnement |
| Coût d'infra ≤ 10 000 €/an | 0 % | Aucun chiffrage |

### Qualité du code (~75 %)

| Critère | Avancement | Détail |
|---|---|---|
| Testé | 70 % | Tests API, store et sous-titres (Whisper mocké) ; pas de tests de charge/perf |
| Maintenable | 90 % | Architecture modulaire `api/` `jobs/` `transcription/` `web/` |
| Évolutif | 80 % | Registre de modèles extensible ; pas de CI/pipeline qualité |

### Industrialisation cloud (~10 %)

| Besoin | Avancement | Détail |
|---|---|---|
| Conteneurisation (Docker) | 0 % | Aucun Dockerfile / docker-compose |
| Déploiement cloud effectif (IaC, VM/K8s) | 0 % | Le lancement documenté est un run Python local |
| CI/CD | 0 % | Aucun workflow trouvé |

## Installation

Prérequis : Python 3.11+, [ffmpeg](https://ffmpeg.org/) dans le `PATH`
(Windows : `winget install ffmpeg`), idéalement un GPU NVIDIA.

```bash
cd Projet
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS : source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install -r ../requirements.txt
```

Les commandes suivantes se lancent depuis `Projet/`.

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
