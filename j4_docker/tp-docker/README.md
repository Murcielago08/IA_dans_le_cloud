# TP Docker — Conteneuriser une API de machine learning

**Durée :** environ 3 h · **Niveau :** débutant Docker, à l'aise en Python

Dans ce TP, vous allez conteneuriser pas à pas une petite application de data science :

- un script **`train.py`** qui entraîne un classifieur sur le jeu de données Iris ;
- une API **FastAPI** (`app.py`) qui sert le modèle et enregistre chaque prédiction dans **PostgreSQL**.

À la fin, toute l'application démarre avec une seule commande : `docker compose up`.

Les numéros de slides renvoient au support de cours.

---

## Prérequis

- Docker Desktop (Windows, Mac) ou Docker Engine (Linux), avec le plugin Compose.
- Vérifiez votre installation :

```bash
docker version
docker compose version
docker run --rm hello-world
```

## Le projet de départ

```
tp-docker/
├── app.py             # l'API : /health, /predict, /predictions
├── train.py           # entraîne le modèle et l'écrit dans models/
├── healthcheck.py     # petit script utilisé par HEALTHCHECK (étape 4)
├── requirements.txt   # dépendances Python, versions épinglées
├── .env.example       # modèle du fichier de secrets (étape 5)
├── data/iris.csv      # 150 fleurs, 4 mesures + l'espèce
└── models/            # vide : le modèle entraîné arrivera ici
```

Prenez cinq minutes pour lire `app.py` et `train.py`. Repérez les variables d'environnement qu'ils lisent : **`MODEL_PATH`**, **`DATA_PATH`** et **`DATABASE_URL`**. Vous en aurez besoin.

> Vous n'avez **pas** besoin d'installer Python ni les dépendances sur votre machine. Tout tournera dans des conteneurs.

---

## Étape 1 — Premier Dockerfile (30 min)

*Slides 12 à 16*

**Objectif :** construire une image qui contient l'API et la lancer.

1. Créez un fichier `Dockerfile` à la racine du projet. Il doit :
   - partir de l'image `python:3.12-slim` ;
   - travailler dans le dossier `/app` ;
   - installer les dépendances de `requirements.txt` avec `pip` (sans cache) ;
   - copier le code ;
   - documenter le port `8000` ;
   - lancer par défaut `uvicorn app:app --host 0.0.0.0 --port 8000`, en **forme exec**.

2. Construisez l'image et nommez-la `iris-api:v1` :

```bash
docker build -t iris-api:v1 .
```

3. Lancez un conteneur en publiant le port 8000 du conteneur sur le port **8080** de votre machine :

```bash
docker run --rm -p 8080:8000 iris-api:v1
```

**Vérification**

- http://localhost:8080/health répond `"status": "ok"`.
- http://localhost:8080/docs affiche l'interface Swagger de FastAPI.
- Dans Swagger, `POST /predict` renvoie une **erreur 503 « Modèle introuvable »**. C'est normal : le modèle n'est pas encore entraîné.

**Questions**

1. Que se passe-t-il si vous oubliez `--host 0.0.0.0` dans la commande uvicorn ? Essayez. Pourquoi ? *(Indice : slide 6, namespace Network.)*
2. Avec `docker image ls`, notez la taille de `iris-api:v1`.
3. Ouvrez un shell dans le conteneur qui tourne avec `docker exec -it <id> bash`. Lancez `ps aux` (ou `cat /proc/1/cmdline`) : quel processus a le PID 1 ?

---

## Étape 2 — Le cache et le .dockerignore (20 min)

*Slide 17*

**Objectif :** comprendre pourquoi l'ordre des instructions change la durée du build.

1. Modifiez une ligne de `app.py` (le titre de l'API par exemple), puis relancez `docker build -t iris-api:v1 .`. Observez les lignes `CACHED` dans la sortie.
2. Inversez maintenant votre Dockerfile pour copier **tout** le code (`COPY . .`) **avant** le `pip install`. Modifiez de nouveau `app.py` et relancez le build.
3. Remettez l'ordre recommandé.
4. Créez un fichier `.dockerignore` qui exclut au moins :
   - `.git`, `__pycache__/` et `.venv/` ;
   - `.env` ;
   - `data/` et `models/`.

**Vérification**

- Avec le bon ordre, une modification de `app.py` ne relance **pas** le `pip install`.
- `docker run --rm iris-api:v1 ls /app` ne montre ni `data/` ni `models/`.

**Questions**

4. Comparez les temps de build des questions 1 et 2. Expliquez la différence.
5. Pourquoi exclure `data/` et `models/` de l'image, alors que l'API en a besoin ? *(Slide 21, et la suite du TP.)*

---

## Étape 3 — Entraîner le modèle dans un conteneur (25 min)

*Slides 20 et 21*

**Objectif :** utiliser des volumes pour les données et le modèle, plutôt que de les copier dans l'image.

1. L'image contient déjà Python et scikit-learn. Utilisez-la pour lancer `train.py` **à la place** de la commande par défaut, en montant :
   - `./data` sur `/app/data`, **en lecture seule** ;
   - `./models` sur `/app/models`, en lecture-écriture.

   La commande à compléter :

```bash
docker run --rm \
  -v ./data:/app/data:ro \
  -v ./models:/app/models \
  iris-api:v1 <commande>
```

2. Vérifiez que `models/model.joblib` est apparu **sur votre machine**.
3. Relancez l'API en montant `./models` en lecture seule, puis testez `/predict` :

```bash
curl -X POST http://localhost:8080/predict \
  -H "Content-Type: application/json" \
  -d '{"sepal_length": 6.7, "sepal_width": 3.0, "petal_length": 5.2, "petal_width": 2.3}'
```

**Vérification**

- Le script affiche une accuracy supérieure à 0,9.
- `/predict` renvoie `{"species": "virginica", "saved": false}`.

**Questions**

6. Comment avez-vous remplacé la commande par défaut ? Que serait-il arrivé si le Dockerfile utilisait `ENTRYPOINT` au lieu de `CMD` ? *(Slide 16.)*
7. Pourquoi est-il préférable d'entraîner le modèle **dans** l'image plutôt que sur votre machine ? *(Pensez à la version de scikit-learn.)*
8. À quoi sert `:ro` sur le dossier `data` ?

---

## Étape 4 — Une image prête pour la prod (25 min)

*Slides 15 et 19*

**Objectif :** appliquer les bonnes pratiques au Dockerfile.

Complétez votre Dockerfile pour :

1. définir la variable d'environnement `PYTHONUNBUFFERED=1`, pour que les `print` s'affichent immédiatement dans les logs ;
2. créer un utilisateur `appuser` (UID 1000) et exécuter l'application avec cet utilisateur ;
3. ajouter un `HEALTHCHECK` toutes les 30 s qui exécute `python healthcheck.py`.

Reconstruisez l'image sous le tag `iris-api:v2` et relancez l'API (avec le volume `models`), cette fois en arrière-plan avec `-d`.

**Vérification**

- `docker ps` affiche `(healthy)` à côté du conteneur, au bout de 30 s environ.
- `docker exec <id> whoami` répond `appuser`.

**Questions**

9. Pourquoi l'image n'utilise-t-elle pas `curl` pour le healthcheck ?
10. Quelle différence entre un conteneur `Up` et un conteneur `Up (healthy)` ?
11. Pourquoi ne faut-il **jamais** mettre `DB_PASSWORD` dans un `ENV` du Dockerfile ? *(Slide 15.)*

---

## Étape 5 — L'API et PostgreSQL avec Compose (40 min)

*Slides 23 à 31*

**Objectif :** décrire l'application complète dans un `compose.yaml`.

1. Copiez `.env.example` en `.env` et choisissez un mot de passe.
2. Créez un fichier `compose.yaml` avec deux services.

   **`db`**
   - image `postgres:16` ;
   - variables `POSTGRES_USER=app`, `POSTGRES_DB=app` et `POSTGRES_PASSWORD`, lue depuis `.env` ;
   - un **volume nommé** `pgdata` monté sur `/var/lib/postgresql/data` ;
   - un **healthcheck** basé sur `pg_isready -U app`.

   **`api`**
   - construit à partir de votre Dockerfile ;
   - port `8000` publié sur `8000` ;
   - `DATABASE_URL` pointant vers la base, **avec le bon nom d'hôte** ;
   - `./models` monté en lecture seule ;
   - démarre **seulement quand la base est prête** ;
   - redémarre automatiquement s'il s'arrête.

3. Lancez l'ensemble avec `docker compose up -d --build`, puis suivez les logs avec `docker compose logs -f api`.

**Vérification**

- `docker compose ps` montre deux services, `db` en `healthy`.
- `/predict` renvoie `"saved": true`.
- Après quelques prédictions, http://localhost:8000/predictions les liste.
- Ouvrez `psql` dans la base et lancez `SELECT count(*) FROM predictions;` :

```bash
docker compose exec db psql -U app -c "SELECT count(*) FROM predictions;"
```

**Persistance**

4. Lancez `docker compose down`, puis `docker compose up -d`. Les prédictions sont-elles toujours là ?
5. Lancez `docker compose down -v`, puis `docker compose up -d`. Et maintenant ?

**Questions**

12. Pourquoi l'API joint-elle la base avec `db:5432` et non `localhost:5432` ?
13. Le port 5432 de la base n'est pas publié sur votre machine. Pourquoi l'API y accède-t-elle quand même ?
14. Que se passe-t-il si vous remplacez la `condition: service_healthy` par un simple `depends_on: [db]` et que vous repartez d'une base vide (`down -v`) ? Regardez les logs de l'API.
15. Lancez `docker compose config`. Que remarquez-vous sur `${DB_PASSWORD}` ?

---

## Étape 6 — Déboguer (15 min)

*Slide 28*

Cassez volontairement l'application, observez, puis réparez.

1. **Mauvais hôte.** Dans `DATABASE_URL`, remplacez `db` par `localhost`, puis relancez avec `docker compose up -d`.
   - Que montrent `docker compose ps` et `docker compose logs api` ?
   - Pourquoi le conteneur redémarre-t-il en boucle ?
2. **Modèle absent.** Supprimez `models/model.joblib` et redémarrez l'API. Quel code HTTP renvoie `/predict` ?
3. Pour les deux cas, notez la commande qui vous a permis de **trouver** le problème.

---

## Bonus — Pour aller plus loin

Choisissez un ou plusieurs bonus.

- **A. Entraînement dans Compose.** Ajoutez un service `train` qui utilise la même image mais lance `python train.py`. L'`api` doit attendre qu'il ait **terminé avec succès** (`condition: service_completed_successfully`).
- **B. Multi-stage build** *(slide 18)*. Réécrivez le Dockerfile en deux étapes : une étape `builder` qui crée un virtualenv dans `/opt/venv`, puis une étape finale qui ne copie que ce virtualenv et le code. Comparez la taille avec `iris-api:v2`.
- **C. Un notebook dans la stack.** Ajoutez un service Jupyter (image `quay.io/jupyter/scipy-notebook`, avec une version épinglée de votre choix) qui monte `./data` et `./notebooks`. Depuis un notebook, interrogez l'API avec `requests.post("http://api:8000/predict", ...)`.
- **D. Stockage objet.** Ajoutez **MinIO** et modifiez `train.py` pour y déposer le modèle au lieu du dossier `models/`.

---

## À rendre

- Votre `Dockerfile`, votre `.dockerignore` et votre `compose.yaml`.
- Les réponses aux questions 1 à 15, deux ou trois lignes chacune.
- **Ne rendez pas** votre `.env`.
