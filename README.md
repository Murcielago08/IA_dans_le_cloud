# Subtitler

Transcription et sous-titrage automatique de vidéos/audios, 100% en interne
(aucun fichier envoyé à un service externe).

Entrée : vidéo `.mp4` ou audio `.wav`. Sortie au choix : vidéo avec sous-titres
incrustés, vidéo + piste de sous-titres, fichier `.srt`, ou texte brut.

Le code applicatif se trouve dans [`Projet/`](Projet/).

## Avancement par rapport au cahier des charges

Référence : [`Projet Fil rouge.pdf`](Projet/Projet%20Fil%20rouge.pdf).
Avancement global estimé : **~82 %** — le pipeline applicatif (API, traitement,
interface, stats), l'identification du locuteur, le dimensionnement de
performance et toutes les nouvelles demandes (marquées 🆕) sont désormais
couverts, ainsi que la conteneurisation (Docker, GPU) et la CI ; il reste le
déploiement effectif sur un serveur cloud et la mesure de performance sur GPU
cloud.

### Besoins fonctionnels obligatoires — Administrateur (~97 %)

| Besoin | Avancement | Détail |
|---|---|---|
| Installer via la documentation | 100 % | Section [Installation](#installation) ci-dessous |
| Arrêter la solution | 100 % | `Ctrl+C` |
| Relancer après arrêt/crash | 100 % | Avec Docker, `restart: unless-stopped` relance le conteneur après un crash ou un redémarrage de la machine ; les traitements interrompus reprennent automatiquement |
| Statistiques d'usage (temps moyen, nb inférences par type, contenu des réponses, non terminés/échoués par type) | 100 % | `GET /api/stats` + page `admin.html` : tous les indicateurs demandés sont présents |
| 🆕 Identification des utilisateurs (comptes, connexion) | 90 % | Comptes + connexion (voir [Comptes utilisateurs](#comptes-utilisateurs)) : chacun ne voit que ses traitements, statistiques réservées à l'administrateur ; reste : réinitialisation du mot de passe, gestion des comptes depuis l'admin, limitation des tentatives de connexion |
| 🆕 Garder une copie interne des fichiers et résultats | 100 % | Tout est conservé dans `data/` : la suppression côté utilisateur ne fait que masquer (voir [Historique et consentement](#historique-et-consentement)) ; l'administrateur voit tous les traitements, y compris retirés, avec le consentement de chacun |
| 🆕 Conservation des données 6 mois maximum | 100 % | Purge automatique au démarrage puis toutes les heures : fichiers, résultats et ligne en base des traitements terminés de plus de 183 jours ; bouton « Purger maintenant » sur la page admin (voir [Conservation des données](#conservation-des-données)) |

### Besoins fonctionnels obligatoires — Utilisateur / Data scientist (~99 %)

| Besoin | Avancement | Détail |
|---|---|---|
| Upload vidéo `.mp4` | 100 % | |
| Upload audio `.wav` | 100 % | |
| Choix du type de résultat selon le tableau du besoin | 100 % | Règles appliquées strictement (`ALLOWED_OUTPUTS`) |
| Lancer le traitement puis télécharger le résultat | 100 % | |
| Ajouter un nouveau modèle de transcription | 100 % | Mécanisme d'extension `register()` documenté (nom affiché, description et langues gérées) |
| Faire évoluer la transcription avec l'identification du speaker | 90 % | Implémenté (voir [Identification du locuteur](#identification-du-locuteur-diarization)) ; reste à valider en conditions réelles (jeton Hugging Face requis, non testé sur GPU faute de matériel ici) |
| 🆕 Choix du modèle dans une pop-up + choix de la langue | 100 % | Pop-up « Langue et modèle » : langue parlée (10 langues ou détection automatique), puis modèle parmi ceux qui la gèrent ; la langue est enregistrée avec le traitement (voir [Modèles et langues](#modèles-et-langues)) |
| 🆕 Plusieurs modèles avec des noms explicites | 100 % | « Rapide », « Équilibré », « Précis », chacun avec une description ; variantes anglaises (`.en`) et multilingues choisies automatiquement selon la langue |
| 🆕 Pagination de l'historique | 100 % | Nombre de traitements par page au choix dans un menu déroulant (5, 10, 50 ou 100, 5 par défaut, mémorisé dans le navigateur), aussi sur la page d'administration, boutons « Précédent » / « Suivant » et compteur « Page 1 / 3 · 25 traitements » ; l'API renvoie le total dans l'en-tête `X-Total-Count` |
| 🆕 Bouton supprimer un téléchargement (masqué pour l'utilisateur seulement) + bouton « tout supprimer » | 100 % | Boutons « Supprimer » et « Tout supprimer » : le traitement disparaît de l'historique de l'utilisateur, les fichiers restent sauvegardés jusqu'à la purge des 6 mois |
| 🆕 Bouton annuler un traitement en attente ou en cours | 100 % | Voir [Annulation](#annulation) : la place se libère aussitôt dans la limite par utilisateur ; une transcription déjà lancée finit son étape avant de s'arrêter |
| 🆕 Case de consentement : conservation de la vidéo à des fins d'analyse et de correction | 100 % | Case facultative à l'envoi (le traitement a lieu dans tous les cas) ; consentement et date enregistrés avec le traitement et visibles par l'administrateur |
| 🆕 Privilégier VLC pour la lecture | 100 % | Recommandé dans l'interface (choix « Vidéo + piste » et sous chaque résultat de ce type, avec lien de téléchargement et marche à suivre) et dans la [documentation](#lire-une-vidéo-avec-piste-de-sous-titres-vlc) |

### Besoins fonctionnels facultatifs (~35 %)

| Besoin | Avancement | Détail |
|---|---|---|
| Consulter le résultat sur l'interface sans le télécharger | 100 % | Bouton « Aperçu » |
| Interfacer la solution au service de traduction | 0 % | Non traité |
| Autre besoin jugé pertinent | — | Non applicable / non défini avec le client |

### Performance & infrastructure (~70 %)

| Besoin | Avancement | Détail |
|---|---|---|
| Traitement plus rapide que la durée de l'échantillon | 70 % | Démontré sur un seul cas mesuré (voir [Performances mesurées](#performances-mesurées)), pas sur l'ensemble des modèles/formats |
| Tenue de la performance jusqu'à 10 utilisateurs en parallèle | 50 % | Architecture de parallélisme prouvée par `tests/test_concurrency.py` et mesurable en conditions réelles avec `scripts/load_test.py` (voir [Performance : parallélisme...](#performance--parallélisme-dimensionnement-et-coût-dinfrastructure)) ; pas encore mesuré sur GPU réel à 10 utilisateurs faute de matériel disponible ici |
| Estimation de l'infrastructure nécessaire | 70 % | Dimensionnement chiffré rédigé (techno d'inférence + techno d'infra + ordre de grandeur de coût) ; à affiner avec une vraie mesure `load_test.py` sur l'offre cloud retenue |
| Coût d'infra ≤ 10 000 €/an | 70 % | Estimé largement sous le budget avec une architecture GPU à la demande (voir détail) ; estimation, pas une facture réelle |
| 🆕 Traitements vidéo en parallèle, max 5 demandes simultanées par utilisateur | 100 % | Traitements en parallèle via `SUBTITLER_WORKERS` ; au-delà de 5 traitements en attente ou en cours, un nouvel envoi est refusé (HTTP 429, message explicite) jusqu'à ce qu'un se termine (voir [Limite par utilisateur](#limite-par-utilisateur)) |

### Qualité du code (~87 %)

| Critère | Avancement | Détail |
|---|---|---|
| Testé | 80 % | Tests API, store, sous-titres et diarization (Whisper mocké) + preuve structurelle de parallélisme (`test_concurrency.py`) ; pas de test de charge GPU réel |
| Maintenable | 90 % | Architecture modulaire `api/` `jobs/` `transcription/` `web/` |
| Évolutif | 90 % | Registre de modèles extensible ; CI GitHub Actions (tests + image Docker) à chaque push |

### Industrialisation cloud (~80 %)

| Besoin | Avancement | Détail |
|---|---|---|
| Conteneurisation (Docker) | 100 % | `Dockerfile` (GPU CUDA ou CPU), `compose.yaml` avec GPU, volumes et relance automatique ; testé de bout en bout dans le conteneur, sur CPU et sur GPU (voir [Docker](#docker)) |
| Déploiement cloud effectif (IaC, VM/K8s) | 60 % | Configuration de production prête et testée en local : HTTPS automatique (Caddy), cookies sécurisés, marche à suivre sur une VM GPU (voir [Déploiement](#déploiement-sur-un-serveur-cloud)) ; reste à la déployer sur un vrai serveur (compte cloud nécessaire), pas d'IaC (Terraform) |
| CI/CD | 80 % | CI GitHub Actions (`.github/workflows/ci.yml`) : tests + construction et démarrage de l'image Docker à chaque push ; pas de déploiement automatique (CD) |

## Installation

Deux possibilités : avec [Docker](#docker) (recommandé pour un serveur), ou
directement avec Python (développement), ci-dessous.

Prérequis : Python 3.11+, [ffmpeg](https://ffmpeg.org/) dans le `PATH`
(Windows : `winget install ffmpeg`), idéalement un GPU NVIDIA.

```bash
cd Projet
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS : source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cu130   # CPU seul : .../whl/cpu
pip install -r requirements-dev.txt
```

`requirements.txt` liste les dépendances de l'application (utilisées par
l'image Docker), `requirements-dev.txt` y ajoute les outils de test. torch
s'installe à part, depuis l'index PyTorch correspondant au matériel.

Les commandes suivantes se lancent depuis `Projet/`.

## Lancer l'application

```bash
python -m subtitler
```

- Interface : <http://127.0.0.1:8000> (redirige vers la page de connexion)
- Admin (statistiques) : <http://127.0.0.1:8000/admin.html>
- Doc de l'API : <http://127.0.0.1:8000/docs>

`Ctrl+C` pour arrêter. Au premier lancement, le modèle Whisper est téléchargé
(~1,5 Go), puis mis en cache. Les traitements interrompus reprennent
automatiquement au redémarrage.

### Créer le compte administrateur

Le compte administrateur (accès aux statistiques et à tous les traitements)
ne se crée pas depuis l'interface : il est créé au démarrage du serveur à
partir de deux variables d'environnement.

1. Se placer dans `Projet/` et activer l'environnement Python :

   ```powershell
   cd Projet
   .venv\Scripts\Activate.ps1          # Linux/macOS : source .venv/bin/activate
   ```

2. Définir l'identifiant et le mot de passe (8 caractères minimum) :

   ```powershell
   # PowerShell
   $env:SUBTITLER_ADMIN_USERNAME = "admin"
   $env:SUBTITLER_ADMIN_PASSWORD = "MonMotDePasse123"
   ```

   ```bash
   # cmd : set SUBTITLER_ADMIN_USERNAME=admin   (sans guillemets ni espaces)
   # Linux/macOS :
   export SUBTITLER_ADMIN_USERNAME=admin
   export SUBTITLER_ADMIN_PASSWORD=MonMotDePasse123
   ```

3. Lancer le serveur **dans le même terminal** : `python -m subtitler`.
4. Ouvrir <http://127.0.0.1:8000> et se connecter avec ces identifiants via
   « Se connecter » (pas « Créer un compte »). Le lien **Administration**
   apparaît dans l'en-tête.

Le compte est enregistré dans la base : aux lancements suivants, les variables
ne sont plus nécessaires. Elles ne durent que le temps du terminal ; pour les
garder, les mettre dans un script de lancement non versionné (il contient le
mot de passe).

**En cas d'échec de connexion** (« Identifiant ou mot de passe incorrect ») :
un compte portant déjà cet identifiant existait sans doute (créé via « Créer
un compte »). Il est bien devenu administrateur, mais garde son ancien mot de
passe : se connecter avec celui-ci, ou relancer avec un autre identifiant
(ex. `$env:SUBTITLER_ADMIN_USERNAME = "superadmin"`).

Configuration par variables d'environnement (valeurs par défaut) :

| Variable | Défaut | Rôle |
|---|---|---|
| `SUBTITLER_HOST` | `127.0.0.1` | Adresse d'écoute (`0.0.0.0` pour le réseau) |
| `SUBTITLER_PORT` | `8000` | Port |
| `SUBTITLER_DATA_DIR` | `data` | Fichiers envoyés, résultats, base SQLite |
| `SUBTITLER_DEFAULT_MODEL` | `whisper-medium.en` | Modèle par défaut |
| `SUBTITLER_DEFAULT_LANGUAGE` | `en` | Langue par défaut (`fr`, `en`... ou `auto`) ; doit être gérée par le modèle par défaut |
| `SUBTITLER_DEVICE` | `cuda:0` | `cpu` pour forcer le CPU |
| `SUBTITLER_WORKERS` | `2` | Utilisateurs traités simultanément (un traitement actif par utilisateur) ; chacun charge son exemplaire du modèle (~1,5 Go de mémoire GPU pour medium) |
| `SUBTITLER_MAX_UPLOAD_MB` | `500` | Taille maximale d'un fichier |
| `SUBTITLER_MAX_JOBS_PER_USER` | `5` | Traitements simultanés (en attente ou en cours) par utilisateur |
| `SUBTITLER_RETENTION_DAYS` | `183` | Durée de conservation des traitements (6 mois), en jours |
| `SUBTITLER_ENABLE_SPEAKERS` | `false` | Active l'identification du locuteur (diarization) |
| `SUBTITLER_DIARIZATION_MODEL` | `pyannote/speaker-diarization-3.1` | Modèle de diarization |
| `SUBTITLER_HF_TOKEN` | — | Jeton Hugging Face requis par le modèle de diarization (gated) |
| `SUBTITLER_ADMIN_USERNAME` | — | Compte administrateur créé au démarrage s'il n'existe pas |
| `SUBTITLER_ADMIN_PASSWORD` | — | Mot de passe de ce compte (8 caractères minimum) |
| `SUBTITLER_ALLOW_SIGNUP` | `true` | `false` pour interdire la création de compte depuis l'interface |
| `SUBTITLER_SESSION_DAYS` | `7` | Durée d'une session de connexion |
| `SUBTITLER_SECURE_COOKIES` | `false` | `true` derrière HTTPS : cookie de session marqué `Secure` |

## Docker

Prérequis : [Docker](https://docs.docker.com/get-docker/) avec Compose et,
pour le GPU, le pilote NVIDIA + le
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
(inclus dans Docker Desktop sous Windows avec WSL 2). Depuis `Projet/` :

```bash
cp .env.example .env        # puis y définir le compte administrateur
docker compose up -d --build
```

- Interface sur <http://127.0.0.1:8000>, comme en lancement Python.
- `docker compose logs -f` pour les logs, `docker compose down` pour arrêter
  (les données sont conservées).
- Sans GPU NVIDIA : `docker compose -f compose.yaml -f compose.cpu.yaml up -d --build`
  (image PyTorch CPU, transcription beaucoup plus lente).

### Commandes Docker

Toutes les commandes `docker compose` se lancent depuis `Projet/`. Compose
nomme ce qu'il crée d'après le dossier : projet `projet`, conteneur
`projet-subtitler-1`, volumes `projet_subtitler-data` et
`projet_subtitler-models`, image `subtitler:latest`.

**Lancer et arrêter**

| Commande | Effet |
|---|---|
| `Copy-Item .env.example .env` (Linux/macOS : `cp`) | Crée le fichier de configuration (une seule fois), à compléter |
| `docker compose up -d --build` | Construit l'image si besoin et lance le conteneur en arrière-plan |
| `docker compose -f compose.yaml -f compose.cpu.yaml up -d --build` | Idem, sans GPU |
| `docker compose restart` | Redémarre le conteneur (après une modification du `.env`) |
| `docker compose stop` | Met le conteneur en pause, sans le supprimer |
| `docker compose start` | Relance un conteneur arrêté par `stop` |
| `docker compose down` | Arrête et supprime le conteneur ; données et modèles conservés |

**Lister ce qui est créé et ce qui tourne**

| Commande | Affiche |
|---|---|
| `docker compose ps` | Le conteneur du projet, son état (`running`, `healthy`...) et ses ports |
| `docker ps` | Tous les conteneurs en cours d'exécution sur la machine |
| `docker ps -a` | Tous les conteneurs, y compris arrêtés |
| `docker images subtitler` | Les images du projet (`latest` GPU, `cpu`, `ci`) et leur taille |
| `docker volume ls --filter name=projet` | Les volumes du projet (données, modèles) |
| `docker compose logs -f` | Les logs en direct (`Ctrl+C` pour quitter, le conteneur continue) |
| `docker stats` | La consommation CPU / mémoire des conteneurs en direct |
| `docker system df` | L'espace disque utilisé par les images, conteneurs et volumes |

**Supprimer**

| Commande | Supprime |
|---|---|
| `docker compose down` | Le conteneur et son réseau ; **garde** les volumes (données, modèles) |
| `docker compose down -v` | Le conteneur **et les volumes** : base, fichiers envoyés, résultats, comptes et modèles téléchargés sont **définitivement perdus** |
| `docker volume rm projet_subtitler-models` | Seulement les modèles téléchargés (retéléchargés au prochain usage) ; conteneur arrêté au préalable |
| `docker image rm subtitler:latest` | L'image GPU (~10 Go) ; reconstruite au prochain `up --build` |
| `docker image rm subtitler:cpu subtitler:ci` | Les images CPU, si elles existent |
| `docker builder prune` | Le cache de construction (accélère les reconstructions, peut peser plusieurs Go) |

Pour effacer uniquement Subtitler et repartir de zéro : `docker compose down -v`
puis `docker image rm subtitler:latest subtitler:ci`.

**Purger tout Docker (toute la machine)**

```powershell
docker system df                 # avant : voir l'espace utilisé
docker volume ls                 # avant : voir les volumes (donc les données) qui vont disparaître
docker stop $(docker ps -q)      # arrêter tous les conteneurs (sinon leurs ressources sont épargnées)
docker system prune -a --volumes # tout supprimer (confirmation demandée : y)
```

`docker system prune -a --volumes` supprime, pour **tous les projets Docker de
la machine** (pas seulement Subtitler) : les conteneurs arrêtés, toutes les
images non utilisées par un conteneur, tous les volumes non utilisés, les
réseaux inutilisés et le cache de construction. Les volumes contiennent les
données (bases, fichiers, comptes, modèles téléchargés) : leur suppression
est **irréversible**.

| Commande | Images | Conteneurs arrêtés | Cache | Volumes (données) |
|---|---|---|---|---|
| `docker system prune -a` | supprimées | supprimés | supprimé | **conservés** |
| `docker system prune -a --volumes` | supprimées | supprimés | supprimé | **supprimés** |

Pour libérer de la place sans perdre de données, préférer
`docker system prune -a` (sans `--volumes`).

| Fichier | Rôle |
|---|---|
| `Dockerfile` | Image Python 3.12 + ffmpeg + PyTorch (CUDA 13.0 par défaut, CPU avec `--build-arg TORCH_INDEX=https://download.pytorch.org/whl/cpu`) ; utilisateur non-root, sonde de santé sur `/api/health` |
| `compose.yaml` | Service avec accès au GPU, relance automatique (`restart: unless-stopped`), volumes `subtitler-data` (base, fichiers, résultats) et `subtitler-models` (modèles téléchargés, pour ne pas les retélécharger) |
| `compose.cpu.yaml` | Variante sans GPU |
| `compose.prod.yaml` | Production : HTTPS automatique avec Caddy (voir [Déploiement](#déploiement-sur-un-serveur-cloud)) |
| `.env.example` | Modèle du fichier `.env` (compte admin, workers, modèle et langue par défaut) ; `.env` n'est jamais versionné |

Vérifié sur la machine de développement : image CPU (2,3 Go) et GPU (9,9 Go,
CUDA visible depuis le conteneur sur RTX 5070) ; un extrait de 15 s est
transcrit et sous-titré de bout en bout dans le conteneur en 66 s sur CPU et
6 s sur GPU. L'image GPU est lourde (bibliothèques CUDA de PyTorch) : la
couche torch reste en cache tant que sa version ne change pas.

## Intégration continue

`.github/workflows/ci.yml` s'exécute sur GitHub à chaque push sur `main`
(et sur les pull requests) qui touche `Projet/` :

1. **Tests** : installe Python 3.12, ffmpeg et `requirements-dev.txt`, puis
   lance `pytest` (sans GPU ni torch : les tests utilisent un faux modèle).
2. **Image Docker** : si les tests passent, construit l'image (variante CPU),
   la démarre et vérifie qu'elle répond (`/api/health`, `/api/info`, page de
   connexion).

Résultat dans l'onglet **Actions** du dépôt GitHub ; un échec est signalé sur
le commit. Lancement manuel possible depuis cet onglet (« Run workflow »).

## Déploiement sur un serveur cloud

La solution se déploie sur une machine virtuelle avec GPU NVIDIA (ex. AWS
g4dn/g5, OVHcloud, Scaleway, Google Cloud), avec la même image Docker :

1. Créer la VM (Ubuntu 24.04, GPU NVIDIA type T4 ou L4) et un nom de domaine
   pointant vers son adresse IP ; ouvrir les ports 80 et 443.
2. Installer le pilote NVIDIA, Docker et le NVIDIA Container Toolkit
   (souvent préinstallés sur les images « Deep Learning » des fournisseurs).
3. Récupérer le projet et configurer :

   ```bash
   git clone https://github.com/Murcielago08/IA_dans_le_cloud.git
   cd IA_dans_le_cloud/Projet
   cp .env.example .env    # mot de passe administrateur solide
   ```

4. Lancer avec HTTPS :

   ```bash
   DOMAIN=subtitler.mon-domaine.fr docker compose -f compose.yaml -f compose.prod.yaml up -d --build
   ```

   Caddy obtient et renouvelle seul le certificat HTTPS (Let's Encrypt),
   redirige HTTP vers HTTPS et transmet les requêtes à l'application, qui
   n'est plus exposée directement ; le cookie de session est marqué `Secure`.

5. Mettre à jour : `git pull` puis la même commande `up -d --build` ; les
   volumes (données, modèles) sont conservés.

Configuration de production testée en local (`DOMAIN=localhost`) : HTTPS,
redirection HTTP → HTTPS, port 8000 fermé, cookie `Secure`. Elle n'a pas été
déployée sur un vrai serveur cloud (compte et nom de domaine nécessaires).
Pistes suivantes : décrire la VM en Terraform (IaC) et ajouter un
déploiement automatique (CD) depuis la CI.

## API

| Route | Accès | Rôle |
|---|---|---|
| `POST /api/auth/register` | public | Crée un compte (`username`, `password`) et ouvre une session |
| `POST /api/auth/login` | public | Ouvre une session : cookie + `token` dans la réponse |
| `POST /api/auth/logout` | connecté | Ferme la session |
| `GET /api/auth/me` | connecté | Utilisateur connecté |
| `POST /api/jobs` | connecté | Envoie un fichier (`file`, `output_kind` ; `model`, `language` et `consent` optionnels) |
| `GET /api/jobs/{id}` | propriétaire | État du traitement + texte transcrit |
| `GET /api/jobs/{id}/result` | propriétaire | Télécharge le résultat (`?inline=true` pour l'afficher) |
| `GET /api/jobs/{id}/subtitles.vtt` | propriétaire | Sous-titres WebVTT |
| `GET /api/jobs` | connecté | Mes traitements, du plus récent au plus ancien (`?all=true` : tous, y compris retirés, administrateur) ; pagination avec `limit`/`offset`, total dans l'en-tête `X-Total-Count` |
| `POST /api/jobs/{id}/cancel` | propriétaire | Annule un traitement en attente ou en cours |
| `DELETE /api/jobs/{id}` | propriétaire | Retire le traitement de l'historique (fichiers conservés) |
| `DELETE /api/jobs` | connecté | Retire tous mes traitements de l'historique (fichiers conservés) |
| `GET /api/stats` | administrateur | Statistiques d'usage |
| `POST /api/admin/purge` | administrateur | Lance tout de suite la purge des données expirées (`{"deleted": n}`) |
| `GET /api/info` | public | Modèles et formats disponibles |
| `GET /api/health` | public | Sonde de santé |

« propriétaire » : l'utilisateur qui a envoyé le fichier, ou l'administrateur.
Le traitement d'un autre utilisateur répond 404, comme s'il n'existait pas.

`output_kind` : `video_embedded`, `video_track`, `subtitles` ou `text`.

```bash
TOKEN=$(curl -s -H "Content-Type: application/json"   -d '{"username": "alice", "password": "mot-de-passe"}'   http://127.0.0.1:8000/api/auth/login | python -c "import json,sys; print(json.load(sys.stdin)['token'])")
curl -H "Authorization: Bearer $TOKEN" -F file=@poc/input.mp4 -F output_kind=subtitles   http://127.0.0.1:8000/api/jobs
```

## Architecture

```
subtitler/
├── api/            FastAPI + service de l'interface web
├── jobs/           modèle de données, SQLite, file d'attente
├── transcription/  modèles de transcription (interface + Whisper)
├── media.py        appels ffmpeg/ffprobe
├── subtitles.py    formats SRT, WebVTT, texte
├── users.py        comptes utilisateurs et sessions
└── web/            interface HTML/CSS/JS (sans build)
```

Un envoi est enregistré puis mis en file d'attente ; un worker extrait l'audio,
transcrit, puis génère le résultat. `SUBTITLER_WORKERS` traitements tournent
en même temps, chacun avec son propre exemplaire du modèle ; au-delà, les
envois attendent leur tour plutôt que de saturer la mémoire du GPU. La file
fait passer les utilisateurs en parallèle, pas leurs fichiers : un
utilisateur n'a qu'un traitement actif à la fois, ses autres fichiers
attendent la fin du précédent, et les workers libres servent les autres
utilisateurs à tour de rôle. Deux utilisateurs qui lancent un traitement en
même temps sont donc traités en parallèle, même si l'un a déjà plusieurs
fichiers en attente.

Ajouter un modèle de transcription :

```python
from subtitler.transcription import Segment, Transcriber, register

class MonModele(Transcriber):
    def transcribe(self, audio_path, language=None):
        # language : « fr », « en »... ou None (détection automatique)
        return [Segment(start=0.0, end=1.5, text="Bonjour")]

register(
    "mon-modele", lambda settings: MonModele(),
    label="Expérimental", description="Mon modèle maison.",
    languages=("fr",),  # None (défaut) : toutes les langues
)
```

Il apparaît alors dans la pop-up de choix (pour les langues qu'il gère) et
dans `/api/info`.

## Lire une vidéo avec piste de sous-titres (VLC)

Le résultat « Vidéo + piste » contient les sous-titres dans une piste séparée
du fichier MP4 (activable / désactivable), et non incrustés dans l'image.
Tous les lecteurs ne savent pas l'afficher : les navigateurs l'ignorent, et le
lecteur de Windows pas toujours. **Lecteur recommandé : [VLC](https://www.videolan.org/vlc/)**
(gratuit, Windows / macOS / Linux) :

1. ouvrir la vidéo téléchargée avec VLC ;
2. si les sous-titres ne s'affichent pas : menu **Sous-titres → Piste de
   sous-titres → Piste 1** (la langue choisie à l'envoi y est indiquée).

L'aperçu dans l'interface affiche quand même les sous-titres : il les charge
à part, au format WebVTT. Pour des sous-titres visibles dans n'importe quel
lecteur, choisir « Vidéo sous-titrée » (sous-titres incrustés dans l'image).

## Modèles et langues

L'utilisateur choisit, dans une pop-up, la langue parlée dans le fichier puis
un modèle parmi ceux qui la gèrent :

| Nom affiché | Anglais | Autres langues | Taille (téléchargée au 1er usage) |
|---|---|---|---|
| Rapide | `whisper-small.en` | `whisper-small` | ~1 Go |
| Équilibré | `whisper-medium.en` | `whisper-medium` | ~3 Go |
| Précis | `whisper-large-v3-turbo` | `whisper-large-v3-turbo` | ~1,6 Go |

- Pour l'anglais, les variantes `.en` (entraînées uniquement sur l'anglais)
  sont plus précises à taille égale ; pour les autres langues ou la détection
  automatique, la pop-up propose les variantes multilingues.
- Langues proposées : français, anglais, espagnol, allemand, italien,
  portugais, néerlandais, arabe, chinois, japonais, ou détection automatique.
- Imposer la langue plutôt que la laisser détecter évite les erreurs quand le
  début du fichier est silencieux, bruité ou dans une autre langue.
- La langue est enregistrée avec le traitement (`language`) et renseignée
  dans la piste de sous-titres des vidéos « vidéo + piste » (lue par VLC).
- L'API refuse une combinaison impossible (ex. `whisper-medium.en` en
  français) avec un message explicite.

## Limite par utilisateur

Un utilisateur peut avoir au plus 5 traitements en attente ou en cours en même
temps (`SUBTITLER_MAX_JOBS_PER_USER`). Au-delà, l'envoi est refusé avec le
code HTTP 429 et le message « Vous avez déjà 5 traitements en cours » ;
l'interface prévient avant même d'envoyer le fichier. Dès qu'un traitement se
termine (réussi ou en échec), une place se libère.

Ces 5 traitements ne tournent pas tous en même temps : un seul est actif, les
autres attendent leur tour, pour que les workers restent disponibles pour les
autres utilisateurs.

- **Pourquoi** : sans limite, un seul utilisateur qui envoie 50 vidéos
  occupe toute la file d'attente et les autres attendent derrière lui. La
  limite garantit qu'avec 10 utilisateurs actifs, chacun garde sa place.
- La limite est vérifiée avant l'enregistrement du fichier (pas de transfert
  inutile), puis à nouveau juste avant la mise en file, sous verrou, pour que
  deux envois parallèles du même utilisateur ne puissent pas la dépasser.
- Un traitement retiré de l'historique compte toujours tant qu'il tourne.
- Le parallélisme effectif (combien de traitements tournent réellement en
  même temps, tous utilisateurs confondus) est réglé par
  `SUBTITLER_WORKERS`, selon la mémoire GPU disponible.

## Annulation

Un bouton « Annuler » apparaît sur chaque traitement en attente ou en cours
(`POST /api/jobs/{id}/cancel`, propriétaire ou administrateur). Le traitement
passe aussitôt à l'état « Annulé » et ne compte plus dans la limite des 5
traitements simultanés.

- **En attente** : il est retiré de la file, il ne démarrera jamais.
- **En cours** : l'annulation est prise en compte entre deux étapes
  (extraction audio, transcription, identification du locuteur, génération du
  résultat). Une étape déjà lancée — notamment la transcription Whisper —
  ne peut pas être interrompue en plein calcul : elle se termine, puis son
  résultat est jeté. Le GPU peut donc rester occupé quelques instants après
  l'annulation.
- Les traitements annulés apparaissent dans les statistiques d'administration
  (colonne « Annulés »), séparément des échecs. Le fichier envoyé reste
  conservé, comme les autres, jusqu'à la purge des 6 mois.

## Conservation des données

Les données d'un traitement (fichier envoyé, résultats, ligne en base) sont
conservées **6 mois** (183 jours, `SUBTITLER_RETENTION_DAYS`) après l'envoi,
puis supprimées définitivement.

- La purge tourne en arrière-plan au démarrage du serveur puis toutes les
  heures ; l'administrateur peut aussi la lancer avec le bouton « Purger
  maintenant » (`POST /api/admin/purge`).
- Elle concerne tous les traitements terminés (réussis, en échec ou annulés),
  y compris ceux retirés de l'historique ou envoyés avec consentement :
  le consentement autorise l'analyse, pas une conservation illimitée.
- Un traitement encore en attente ou en cours n'est jamais purgé.
- Les fichiers sont supprimés avant la ligne en base : si un fichier ne peut
  pas être effacé (verrouillé par exemple), la ligne reste et la purge
  suivante réessaie, sans laisser de fichiers orphelins.
- Les comptes utilisateurs ne sont pas concernés ; les statistiques
  d'administration ne portent que sur les traitements encore conservés.

## Historique et consentement

- **Consentement** : une case facultative du formulaire d'envoi permet à
  l'utilisateur d'accepter que son fichier soit conservé à des fins d'analyse
  et de correction de la transcription. Elle n'est pas obligatoire : selon le
  RGPD, un consentement n'est valable que s'il est libre, donc le refuser ne
  doit pas empêcher d'utiliser le service. Le choix et sa date sont
  enregistrés avec le traitement (`consent`, `consent_at`) ; seuls les
  fichiers avec `consent = true` peuvent servir à l'analyse.
- **Suppression** : « Supprimer » et « Tout supprimer » retirent les
  traitements de l'historique de l'utilisateur (`hidden_at`), qui ne peut plus
  y accéder. Rien n'est effacé sur le serveur : fichiers et résultats restent
  sauvegardés jusqu'à la purge des 6 mois, et l'administrateur les voit
  toujours, marqués « retiré par l'utilisateur ».

## Comptes utilisateurs

Chaque utilisateur se connecte avec un identifiant et un mot de passe (page
`login.html`, ou création de compte si `SUBTITLER_ALLOW_SIGNUP` le permet). Il
ne voit et ne télécharge que ses propres traitements, et retrouve son
historique sur n'importe quel appareil (il était auparavant gardé dans le
navigateur). Le compte administrateur, défini par variables d'environnement,
voit tous les traitements et les statistiques.

- **Mots de passe** : hachés avec scrypt (bibliothèque standard Python, sel
  aléatoire par compte) ; jamais stockés en clair.
- **Sessions** : jeton aléatoire envoyé dans un cookie `HttpOnly` +
  `SameSite=Lax` (illisible par JavaScript, non envoyé par un autre site), ou
  dans l'en-tête `Authorization: Bearer` pour les scripts. Seule l'empreinte
  SHA-256 du jeton est stockée en base ; les sessions expirent après
  `SUBTITLER_SESSION_DAYS` jours.
- **Pourquoi pas un fournisseur d'identité externe (Keycloak, Auth0, SSO)** :
  plus lourd à installer, et Auth0 enverrait des données hors de
  l'infrastructure, contraire au besoin « 100 % en interne ». Les comptes
  locaux suffisent pour le besoin ; un SSO d'entreprise pourra être branché
  plus tard devant l'API.
- Les traitements créés avant l'ajout des comptes n'ont pas de propriétaire :
  seul l'administrateur les voit.
- Derrière HTTPS, `SUBTITLER_SECURE_COOKIES=true` marque le cookie `Secure`
  (jamais envoyé en clair) ; c'est automatique avec `compose.prod.yaml`.

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

L'architecture (file d'attente `JobStore` + pool de threads `JobWorker`,
taille réglée par `SUBTITLER_WORKERS`) traite N jobs en parallèle, un thread
par worker, et la transcription elle-même est parallèle : `WhisperTranscriber`
charge jusqu'à N exemplaires du modèle (à la demande) et chaque thread en
réserve un pendant sa transcription. La file (`FairQueue`) ne donne
qu'un worker à la fois à chaque utilisateur et sert les utilisateurs à tour de
rôle : aucun ne peut monopoliser les workers en envoyant plusieurs fichiers.
`tests/test_concurrency.py` et `tests/test_scheduling.py` le démontrent sans
GPU : 5 jobs à délai fixe soumis en même temps se terminent en ~1x ce délai,
pas 5x.

Limite à connaître : sur **un seul GPU**, plusieurs exemplaires tournent en
même temps mais se partagent sa puissance de calcul. Chaque traitement
avance, mais un peu moins vite que s'il était seul ; le gain vient surtout
de ce que le GPU est mal occupé par une seule transcription (génération mot
par mot). Le nombre de workers est borné par la mémoire GPU : ~1,5 Go par
exemplaire de `whisper-medium.en` en float16, donc 2 à 3 sur une carte de
8 Go. Au-delà, il faut plusieurs GPU ou `faster-whisper` (modèle plus léger,
voir ci-dessous).

`scripts/load_test.py` permet de mesurer, sur le matériel cible, le temps de
traitement bout en bout pour N requêtes simultanées et de le comparer à la
durée de l'échantillon :

```bash
python scripts/load_test.py poc/input.mp4 --concurrency 10
```

Chaque utilisateur simulé utilise son propre compte (`loadtest-0` à
`loadtest-9`, créés automatiquement), comme 10 vrais utilisateurs.

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

### Lancer les tests automatiques

Les tests sont écrits et lancés avec **[pytest](https://docs.pytest.org/)** :
la commande `pytest` trouve les fichiers `test_*.py`, exécute chaque test et
affiche le résultat. pytest fait partie des dépendances du projet
(`requirements-dev.txt`) : il est installé par `pip install -r requirements-dev.txt`
(voir [Installation](#installation)), rien de plus à installer.

Prérequis : l'environnement Python installé (voir [Installation](#installation))
et ffmpeg dans le `PATH`. Pas besoin de GPU ni de télécharger de modèle :
Whisper est remplacé par un faux modèle, les tests tournent en ~15 secondes.

1. Activer l'environnement Python :

   ```powershell
   .venv\Scripts\Activate.ps1          # Linux/macOS : source .venv/bin/activate
   ```

2. Lancer tous les tests, depuis la racine du dépôt ou depuis `Projet/` (le
   `pytest.ini` à la racine pointe vers `Projet/tests`) :

   ```bash
   pytest
   ```

   Si Windows répond que `pytest` est introuvable, c'est que l'environnement
   n'est pas activé (étape 1). Sans l'activer, la commande équivalente est
   `.venv\Scripts\python -m pytest`.

3. Lire le résultat : la dernière ligne doit indiquer `N passed` sans
   `failed`. Des tests `skipped` signifient en général que ffmpeg est absent :
   ils n'ont alors pas été vérifiés.

Options utiles :

| Commande | Effet |
|---|---|
| `pytest -v` | Affiche le nom et le résultat de chaque test |
| `pytest -x` | S'arrête au premier échec |
| `pytest Projet/tests/test_auth.py` | Lance un seul fichier |
| `pytest -k cancel` | Lance les tests dont le nom contient « cancel » |

Contenu de `Projet/tests/` :

| Fichier | Ce qui est testé |
|---|---|
| `test_api.py` | Envoi de fichiers, résultats, formats, erreurs |
| `test_auth.py` | Comptes, connexion, droits administrateur |
| `test_history.py` | Consentement, suppression de l'historique, pagination |
| `test_limits.py` | Limite de 5 traitements par utilisateur |
| `test_cancel.py` | Annulation d'un traitement |
| `test_scheduling.py` | File équitable entre utilisateurs, exemplaires du modèle |
| `test_concurrency.py` | Traitements en parallèle |
| `test_models.py` | Catalogue des modèles et choix de la langue |
| `test_retention.py` | Purge des données à 6 mois |
| `test_store.py` | Base de données et statistiques |
| `test_subtitles.py` | Formats SRT, WebVTT et texte |
| `test_diarization.py` | Identification du locuteur |

### Test de charge (à part)

`pytest` ne lance **pas** `scripts/load_test.py` : ce test mesure les vraies
performances (vrai modèle, vrai GPU) contre un serveur démarré, et prend
plusieurs minutes. À lancer à la main, dans deux terminaux :

```bash
# Terminal 1, depuis Projet/
python -m subtitler

# Terminal 2, depuis Projet/ : 10 utilisateurs simultanés
python scripts/load_test.py poc/input.mp4 --concurrency 10
```

Voir [Parallélisme](#parallélisme-tenue-à-10-utilisateurs-simultanés) pour
l'interprétation des résultats.

## Performances mesurées

RTX 3060 Laptop (6 Go), `whisper-medium.en`, vidéo de 2 min 29 s : 41 s de
traitement une fois le modèle chargé (28 % de la durée de la vidéo).
