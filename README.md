# Subtitler

Transcription et sous-titrage automatique de vidéos/audios, 100% en interne
(aucun fichier envoyé à un service externe).

Entrée : vidéo `.mp4` ou audio `.wav`. Sortie au choix : vidéo avec sous-titres
incrustés, vidéo + piste de sous-titres, fichier `.srt`, ou texte brut.

Le code applicatif se trouve dans [`Projet/`](Projet/).

## Avancement par rapport au cahier des charges

Référence : [`Projet Fil rouge.pdf`](Projet/Projet%20Fil%20rouge.pdf).
Avancement global estimé : **~68 %** — le pipeline applicatif (API, traitement,
interface, stats), l'identification du locuteur et le dimensionnement de
performance sont désormais couverts ; le volet *industrialisation cloud*
(conteneurisation, déploiement effectif, CI) reste largement à faire.

### Besoins fonctionnels obligatoires — Administrateur (~95 %)

| Besoin | Avancement | Détail |
|---|---|---|
| Installer via la documentation | 100 % | Section [Installation](#installation) ci-dessous |
| Arrêter la solution | 100 % | `Ctrl+C` |
| Relancer après arrêt/crash | 90 % | Les traitements interrompus reprennent automatiquement au redémarrage ; pas de superviseur (systemd/Docker restart) pour un redémarrage *automatique* après crash sans action humaine |
| Statistiques d'usage (temps moyen, nb inférences par type, contenu des réponses, non terminés/échoués par type) | 100 % | `GET /api/stats` + page `admin.html` : tous les indicateurs demandés sont présents |

### Besoins fonctionnels obligatoires — Utilisateur / Data scientist (~95 %)

| Besoin | Avancement | Détail |
|---|---|---|
| Upload vidéo `.mp4` | 100 % | |
| Upload audio `.wav` | 100 % | |
| Choix du type de résultat selon le tableau du besoin | 100 % | Règles appliquées strictement (`ALLOWED_OUTPUTS`) |
| Lancer le traitement puis télécharger le résultat | 100 % | |
| Ajouter un nouveau modèle de transcription | 100 % | Mécanisme d'extension `register()` documenté |
| Faire évoluer la transcription avec l'identification du speaker | 90 % | Implémenté (voir [Identification du locuteur](#identification-du-locuteur-diarization)) ; reste à valider en conditions réelles (jeton Hugging Face requis, non testé sur GPU faute de matériel ici) |

### Besoins fonctionnels facultatifs (~35 %)

| Besoin | Avancement | Détail |
|---|---|---|
| Consulter le résultat sur l'interface sans le télécharger | 100 % | Bouton « Aperçu » |
| Interfacer la solution au service de traduction | 0 % | Non traité |
| Autre besoin jugé pertinent | — | Non applicable / non défini avec le client |

### Performance & infrastructure (~55 %)

| Besoin | Avancement | Détail |
|---|---|---|
| Traitement plus rapide que la durée de l'échantillon | 70 % | Démontré sur un seul cas mesuré (voir [Performances mesurées](#performances-mesurées)), pas sur l'ensemble des modèles/formats |
| Tenue de la performance jusqu'à 10 utilisateurs en parallèle | 50 % | Architecture de parallélisme prouvée par `tests/test_concurrency.py` et mesurable en conditions réelles avec `scripts/load_test.py` (voir [Performance : parallélisme...](#performance--parallélisme-dimensionnement-et-coût-dinfrastructure)) ; pas encore mesuré sur GPU réel à 10 utilisateurs faute de matériel disponible ici |
| Estimation de l'infrastructure nécessaire | 70 % | Dimensionnement chiffré rédigé (techno d'inférence + techno d'infra + ordre de grandeur de coût) ; à affiner avec une vraie mesure `load_test.py` sur l'offre cloud retenue |
| Coût d'infra ≤ 10 000 €/an | 70 % | Estimé largement sous le budget avec une architecture GPU à la demande (voir détail) ; estimation, pas une facture réelle |

### Qualité du code (~80 %)

| Critère | Avancement | Détail |
|---|---|---|
| Testé | 80 % | Tests API, store, sous-titres et diarization (Whisper mocké) + preuve structurelle de parallélisme (`test_concurrency.py`) ; pas de test de charge GPU réel |
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
| `SUBTITLER_ENABLE_SPEAKERS` | `false` | Active l'identification du locuteur (diarization) |
| `SUBTITLER_DIARIZATION_MODEL` | `pyannote/speaker-diarization-3.1` | Modèle de diarization |
| `SUBTITLER_HF_TOKEN` | — | Jeton Hugging Face requis par le modèle de diarization (gated) |

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

## Identification du locuteur (diarization)

Fonctionnalité optionnelle, désactivée par défaut (`SUBTITLER_ENABLE_SPEAKERS=true`
pour l'activer). Répond au besoin « compte rendu automatique de réunion » et à
l'évolution explicitement demandée au data scientist dans le cahier des charges.

**Technologie : [`pyannote.audio`](https://github.com/pyannote/pyannote-audio)**
(pipeline de diarization pré-entraîné).

- **Comment ça marche (courte définition)** : le pipeline détecte d'abord les
  zones de parole (détection d'activité vocale), calcule une *empreinte
  vocale* (embedding) sur des fenêtres glissantes du signal, puis regroupe
  (clustering) les fenêtres dont l'empreinte se ressemble pour déterminer qui
  parle à quel instant — indépendamment du texte. Le résultat (des tours de
  parole `SPEAKER_00`, `SPEAKER_01`, ...) est ensuite recoupé avec les
  segments transcrits par Whisper selon leur chevauchement temporel
  (`assign_speakers` dans `subtitler/transcription/diarization.py`) : chaque
  segment de texte hérite du locuteur dont le tour de parole le recouvre le
  plus.
- **Pourquoi celle-ci et pas une autre** :
  - vs un **clustering maison sur l'énergie/le pitch du signal** : peu fiable
    dès que deux voix ont une tonalité proche ou qu'il y a du bruit de fond —
    pas assez robuste pour de la production.
  - vs **Resemblyzer** (embeddings de voix seuls, sans pipeline complet) : il
    faudrait implémenter et régler soi-même la détection d'activité vocale et
    le clustering, pour un résultat moins précis.
  - vs **NVIDIA NeMo / SpeechBrain** : solutions valables mais dépendances
    plus lourdes à installer, ou pipeline moins directement utilisable.
  - **`pyannote.audio`** fournit un pipeline complet prêt à l'emploi (VAD +
    embeddings + clustering), reconnu comme état de l'art sur les benchmarks
    publics de diarization, tourne 100 % en local (cohérent avec le besoin de
    souveraineté du projet), et suit le même schéma que `WhisperTranscriber`
    (chargement paresseux, GPU optionnel).
  - Contrepartie assumée : le modèle est *gated* sur Hugging Face (licence à
    accepter une fois, gratuitement, puis jeton `SUBTITLER_HF_TOKEN`) — c'est
    le principal frein à l'activer par défaut pour tout le monde.

**Intégration dans le code existant** : `Segment` porte un champ
`speaker: str | None` ; `subtitles.py` préfixe le texte par `[SPEAKER_XX]`
quand il est renseigné (SRT, VTT et texte brut) ; `JobWorker` appelle le
diarizer juste après la transcription, uniquement si l'option est activée.
Ajouter un autre modèle de diarization suit le même principe que pour la
transcription : implémenter `Diarizer.diarize()`.

## Performance : parallélisme, dimensionnement et coût d'infrastructure

### Parallélisme (tenue à 10 utilisateurs simultanés)

L'architecture existante (file d'attente `JobStore` + pool de threads
`JobWorker`, taille réglée par `SUBTITLER_WORKERS`) traite déjà N jobs en
parallèle, un thread par worker. `tests/test_concurrency.py` le démontre
structurellement, sans GPU : 5 jobs à délai fixe soumis en même temps se
terminent en ~1x ce délai, pas 5x. Ce qui reste à valider, c'est la capacité
GPU réelle derrière chaque worker — un thread ne sert à rien si un seul GPU
physique doit déjà traiter plusieurs vidéos à la fois.

`scripts/load_test.py` permet de mesurer, sur le matériel cible, le temps de
traitement bout en bout pour N requêtes simultanées et de le comparer à la
durée de l'échantillon :

```bash
python scripts/load_test.py poc/input.mp4 --concurrency 10
```

### Technologies retenues pour tenir la charge au coût visé

**Moteur d'inférence : [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper)
(CTranslate2)**, en remplacement du pipeline `transformers` actuel pour la mise
en production à charge.

- **Comment ça marche (courte définition)** : CTranslate2 réexporte les poids
  du modèle Whisper dans un format optimisé et quantifié (int8/float16), ce
  qui réduit la mémoire GPU utilisée et accélère l'inférence (de l'ordre de
  3 à 4x plus rapide que `transformers`, à qualité de transcription égale).
  Moins de mémoire par instance de modèle chargée veut dire plus d'instances
  tenues en parallèle sur un même GPU.
- **Pourquoi celle-ci et pas une autre** :
  - vs **`transformers` (utilisé actuellement)** : simple et déjà en place,
    mais plus gourmand en mémoire et plus lent — suffisant pour un usage
    mono-utilisateur, limitant pour tenir 10 utilisateurs sur peu de GPU.
  - vs **`whisper.cpp`** : excellent sur CPU, mais ne tire pas aussi bien
    parti d'un GPU pour du volume — pertinent seulement pour du edge/CPU-only,
    pas le scénario ici.
  - **`faster-whisper`** est un remplacement direct, sans changer
    l'architecture du projet : il suffit d'ajouter un
    `FasterWhisperTranscriber` au registre existant
    (`subtitler/transcription/registry.py`), sans toucher à l'API ni au
    worker.

**Infrastructure : GPU à la demande (serverless/autoscaling)**, plutôt qu'une
VM GPU dédiée allumée 24 h/24.

- **Comment ça marche (courte définition)** : des offres comme AWS SageMaker
  Serverless Inference, Modal ou RunPod Serverless allouent un GPU à la
  demande pour la durée du traitement puis le libèrent aussitôt — facturation
  à la seconde d'usage réel, pas à l'heure de disponibilité.
- **Pourquoi celle-ci et pas une autre** :
  - vs une **VM GPU dédiée 24 h/24** (ex. AWS g5.xlarge, ≈ 1 €/h) : environ
    8 760 €/an pour une seule carte en permanence — dépasse déjà le budget à
    elle seule, alors que l'usage réel attendu (sous-titrage à la demande, pas
    un flux continu) n'occupe qu'une fraction de la journée.
  - vs un **groupe auto-scalé de VMs classiques** : le démarrage d'une VM GPU
    (drivers, image système, plusieurs minutes) est trop lent pour des jobs
    ponctuels de quelques dizaines de secondes à quelques minutes.
  - Le **GPU serverless** ne coûte rien tant que personne n'utilise le
    service (cas majoritaire attendu ici), seule façon réaliste de tenir un
    pic à 10 utilisateurs en parallèle sous 10 000 €/an sans sur-provisionner
    en continu.

### Estimation chiffrée (ordre de grandeur)

Base : mesure déjà réalisée (RTX 3060 Laptop, `whisper-medium.en`, ratio 28 %
temps réel, voir [Performances mesurées](#performances-mesurées)). Avec
`faster-whisper` sur un GPU cloud équivalent ou supérieur (NVIDIA T4/A10G), on
vise un ratio ≤ 10-15 %, ce qui laisse de la marge pour traiter plusieurs
requêtes en léger différé sur un même GPU sans dépasser la durée de
l'échantillon.

| Hypothèse | Valeur |
|---|---|
| Tarif GPU serverless (T4/A10G), à l'usage | ≈ 0,50 à 1,00 €/h équivalent |
| Usage réel estimé (pics ponctuels, pas 24 h/24) | ≈ 150 à 300 h/an cumulées sur tous les traitements |
| Coût annuel estimé | ≈ 150 à 300 € — large marge sous les 10 000 €/an |

Ces chiffres sont des ordres de grandeur à affiner avec une vraie mesure de
`scripts/load_test.py` sur l'offre cloud retenue ; ils montrent surtout que
l'enjeu budgétaire n'est pas le prix du GPU mais le modèle de facturation (à
l'usage réel, pas à la disponibilité permanente).

## Tests

```bash
pytest
```

Fonctionne aussi bien depuis `Projet/` que depuis la racine du dépôt (le
`pytest.ini` à la racine pointe vers `Projet/tests`). Whisper est remplacé par
un faux modèle : les tests tournent en quelques secondes, sans GPU (ffmpeg
requis). `scripts/load_test.py` (voir ci-dessus) est un test de charge
séparé, à lancer à la main contre une vraie instance.

## Performances mesurées

RTX 3060 Laptop (6 Go), `whisper-medium.en`, vidéo de 2 min 29 s : 41 s de
traitement une fois le modèle chargé (28 % de la durée de la vidéo).
