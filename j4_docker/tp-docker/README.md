## Commandes pour lancer

À lancer depuis le dossier `j4_docker/tp-docker`.

```bash
# 1. Construire l'image
docker build -t iris-api:v1 .

# 2a. Lancer au premier plan (logs dans le terminal, Ctrl+C pour arrêter)
docker run --rm -p 8080:8000 iris-api:v1

# 2b. Ou lancer en arrière-plan
docker run -d --rm -p 8080:8000 --name iris iris-api:v1

# 3. Tester : http://localhost:8080/health et http://localhost:8080/docs

# 4. Suivre / arrêter un conteneur en arrière-plan
docker logs -f iris            # logs en direct
docker exec -it iris bash      # shell dans le conteneur
docker stop iris               # arrêter (--rm le supprime aussi)

- `-t iris-api:v1` : nom et tag de l'image ; `.` : le dossier qui contient le Dockerfile.
- `-p 8080:8000` : port 8000 du conteneur publié sur le port 8080 de la machine.
- `--rm` : supprime le conteneur à l'arrêt ; `-d` : arrière-plan ; `--name` : nom du conteneur.
- Port 8080 déjà pris : utiliser `-p 8081:8000`, ou arrêter l'ancien conteneur (`docker ps` puis `docker stop <id>`).

docker ps                      # conteneurs en cours d'exécution
docker ps -a                   # tous les conteneurs, y compris ceux arrêtés
docker image ls                # toutes les images
docker image ls iris-api       # seulement les images iris-api


docker stop $(docker ps -q)
docker stop <id_ou_nom>        # arrêter le conteneur
docker rm -f $(docker ps -aq)    # arrête et supprime tous les conteneurs, même ceux déjà arrêtés
docker rm <id_ou_nom>          # le supprimer (il doit être arrêté)
docker rm -f <id_ou_nom>       # arrêter et supprimer en une seule commande
docker image rm iris-api:v1    # ou : docker rmi iris-api:v1
docker rm -f $(docker ps -aq)          # 1. supprimer tous les conteneurs
docker rmi -f $(docker images -q)      # 2. supprimer toutes les images

docker container prune         # supprime tous les conteneurs arrêtés
docker image prune             # supprime les images sans tag (<none>)
docker system prune            # conteneurs arrêtés, réseaux inutilisés, images sans tag et cache de build
docker system prune -a           # supprime les conteneurs arrêtés, toutes les images inutilisées, les réseaux et le cache de build
docker system prune -a --volumes # et en plus tous les volumes inutilisés (dont la base pgdata)
docker volume prune -a                  # supprime tous les volumes inutilisés, y compris les volumes nommés
docker volume rm $(docker volume ls -q) # supprime tous les volumes
docker system df               # voir l'espace disque utilisé par Docker
```

---

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

Sans --host 0.0.0.0, uvicorn écoute sur 127.0.0.1 par défaut. Or chaque conteneur a son propre namespace réseau, donc son propre localhost, distinct de celui de ta machine. Les requêtes publiées avec -p arrivent sur l'interface réseau du conteneur, pas sur son localhost, et la connexion échoue. Avec 0.0.0.0, uvicorn écoute sur toutes les interfaces du conteneur.

2. Avec `docker image ls`, notez la taille de `iris-api:v1`.

docker image ls iris-api : l'image iris-api:v1 fait 702 Mo sur le disque (163 Mo compressés). L'image de base python:3.12-slim fait environ 130 Mo, et pandas, scikit-learn, numpy et scipy ajoutent le reste.

3. Ouvrez un shell dans le conteneur qui tourne avec `docker exec -it <id> bash`. Lancez `ps aux` (ou `cat /proc/1/cmdline`) : quel processus a le PID 1 ?

Le processus de PID 1 : lance docker ps pour trouver l'id du conteneur, puis docker exec -it <id> bash et cat /proc/1/cmdline. Tu devrais voir uvicorn (/usr/local/bin/python /usr/local/bin/uvicorn app:app --host 0.0.0.0 --port 8000), grâce à la forme exec. En forme shell (CMD uvicorn ...), le PID 1 serait /bin/sh -c. ps n'est pas installé dans l'image slim, c'est pour ça que l'énoncé propose /proc/1/cmdline en alternative.

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

Pourquoi les temps de build sont si différents. Chaque instruction crée une couche, et Docker réutilise le cache d'une couche tant que ni elle ni les couches précédentes n'ont changé. Pour un COPY, Docker compare le contenu des fichiers copiés.

Avec le bon ordre, requirements.txt ne change pas, donc la couche pip install reste en cache. Seul COPY . . est refait, ce qui prend 0,7 s.
Avec l'ordre inversé, modifier app.py invalide COPY . ., et donc toutes les couches qui suivent, y compris le pip install. Le build prend alors 25 s à chaque modification du code.
En résumé, on place en haut ce qui change rarement et en bas ce qui change souvent.

5. Pourquoi exclure `data/` et `models/` de l'image, alors que l'API en a besoin ? *(Slide 21, et la suite du TP.)*

Pourquoi exclure data/ et models/ alors que l'API en a besoin. L'image doit contenir le code et l'environnement, pas les données ni le modèle :

Taille et reconstruction : un gros jeu de données ou un nouveau modèle gonflerait l'image et obligerait à la reconstruire à chaque réentraînement.
Séparation des rôles : la même image doit pouvoir servir n'importe quelle version du modèle. On fournit le modèle au lancement par un volume (étape 3), ou plus tard par un stockage objet (bonus D).
Sécurité : les données peuvent être sensibles. C'est la même logique que pour .env, qu'on ne met jamais dans une image.

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

On ajoute la commande après le nom de l'image : `docker run --rm -v ./data:/app/data:ro -v ./models:/app/models iris-api:v1 python train.py`. Tout ce qui suit le nom de l'image remplace le CMD : le conteneur lance l'entraînement au lieu d'uvicorn, puis s'arrête.
Avec un ENTRYPOINT ["uvicorn", ...], ces mots seraient ajoutés comme arguments à l'ENTRYPOINT : Docker lancerait `uvicorn app:app ... python train.py`, ce qui échouerait. Pour remplacer un ENTRYPOINT, il faut le préciser explicitement : `--entrypoint python ... iris-api:v1 train.py`.

7. Pourquoi est-il préférable d'entraîner le modèle **dans** l'image plutôt que sur votre machine ? *(Pensez à la version de scikit-learn.)*

Un fichier .joblib est un objet Python sérialisé (pickle), lié à la version de scikit-learn qui l'a créé. En entraînant dans l'image, le modèle est produit avec exactement la même version que celle qui le charge dans l'API (1.5.2, figée dans requirements.txt). On évite ainsi les avertissements ou erreurs de chargement dus à une version différente sur la machine. En plus, l'entraînement est reproductible chez n'importe qui, sans rien installer.

8. À quoi sert `:ro` sur le dossier `data` ?

:ro monte le dossier en lecture seule : le conteneur peut lire les données mais ni les modifier ni les supprimer, même par erreur ou à cause d'un bug du script. Vérifié : une écriture dans un volume monté en :ro échoue avec « Read-only file system ».

Résultats obtenus : accuracy de 0,933 sur le jeu de test, models/model.joblib (2 Ko) apparu sur la machine, et /predict renvoie {"species":"virginica","saved":false}.

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

L'image python:3.12-slim ne contient pas curl. L'installer (apt-get install curl) ajouterait des Mo et des paquets, donc plus de failles possibles, juste pour un test. Python est déjà dans l'image : healthcheck.py fait la même requête avec urllib (bibliothèque standard) et renvoie le code de sortie 0 ou 1 attendu par HEALTHCHECK.

10. Quelle différence entre un conteneur `Up` et un conteneur `Up (healthy)` ?

Up veut seulement dire que le processus principal (PID 1) tourne. Up (healthy) veut dire en plus que le HEALTHCHECK réussit : l'API répond vraiment sur /health. Un conteneur peut être Up alors que l'application est bloquée ou encore en démarrage (health: starting) ou en panne (unhealthy). Compose s'appuie sur cet état avec condition: service_healthy. Vérifié : (health: starting) au lancement, puis (healthy) après ~30 s.

11. Pourquoi ne faut-il **jamais** mettre `DB_PASSWORD` dans un `ENV` du Dockerfile ? *(Slide 15.)*

Un ENV est gravé dans l'image : n'importe qui ayant accès à l'image peut le lire avec docker image inspect ou docker history, et il part avec l'image sur un registry. Il faudrait aussi reconstruire l'image pour changer le mot de passe, et le même secret serait partagé entre dev et prod. Le secret doit être fourni au lancement (fichier .env non versionné, variables d'environnement, ou secrets Docker).

Dockerfile final : ENV PYTHONUNBUFFERED=1, useradd --uid 1000 appuser puis USER appuser, et HEALTHCHECK --interval=30s CMD ["python", "healthcheck.py"]. Vérifié : docker ps affiche « Up 40 seconds (healthy) » et docker exec iris whoami répond appuser.

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

Oui : 4 prédictions avant, 4 après. down supprime les conteneurs et le réseau, mais pas le volume nommé pgdata, où PostgreSQL stocke ses données.

5. Lancez `docker compose down -v`, puis `docker compose up -d`. Et maintenant ?

Non : 0 prédiction. -v supprime aussi les volumes nommés : la base repart de zéro et l'API recrée une table vide au démarrage.

Résultats obtenus : docker compose ps montre db en (healthy) et api Up, /predict renvoie "saved": true, /predictions liste les prédictions et SELECT count(*) renvoie 4 après 4 prédictions.

**Questions**

12. Pourquoi l'API joint-elle la base avec `db:5432` et non `localhost:5432` ?

Chaque conteneur a son propre namespace réseau : dans le conteneur api, localhost désigne le conteneur api lui-même, où aucune base n'écoute. Compose crée un réseau commun aux services et un DNS interne qui résout le nom du service (db) vers l'IP du conteneur de la base.

13. Le port 5432 de la base n'est pas publié sur votre machine. Pourquoi l'API y accède-t-elle quand même ?

Publier un port (ports:) sert seulement à l'ouvrir depuis la machine hôte. Entre conteneurs du même réseau Compose, tous les ports sont accessibles directement. C'est même mieux pour la sécurité : la base n'est pas joignable depuis l'extérieur, seule l'API y accède.

14. Que se passe-t-il si vous remplacez la `condition: service_healthy` par un simple `depends_on: [db]` et que vous repartez d'une base vide (`down -v`) ? Regardez les logs de l'API.

depends_on: [db] attend seulement que le conteneur db soit démarré, pas que PostgreSQL soit prêt. Sur une base vide, PostgreSQL met quelques secondes à s'initialiser : l'API démarre trop tôt et plante au démarrage. Logs observés : « psycopg.OperationalError: connection failed: ... port 5432 failed: Connection refused », puis l'API redémarre (restart: unless-stopped) et le 2e essai réussit (« Connexion à PostgreSQL OK »). Sans politique restart, l'API resterait arrêtée.

15. Lancez `docker compose config`. Que remarquez-vous sur `${DB_PASSWORD}` ?

Compose remplace ${DB_PASSWORD} par sa valeur lue dans .env : le mot de passe apparaît en clair dans DATABASE_URL et POSTGRES_PASSWORD. docker compose config montre la configuration finale réellement utilisée, c'est utile pour vérifier les variables, mais il ne faut pas partager sa sortie : elle contient les secrets. De même, le mot de passe reste visible avec docker inspect.

---

## Étape 6 — Déboguer (15 min)

*Slide 28*

Cassez volontairement l'application, observez, puis réparez.

1. **Mauvais hôte.** Dans `DATABASE_URL`, remplacez `db` par `localhost`, puis relancez avec `docker compose up -d`.
   - Que montrent `docker compose ps` et `docker compose logs api` ?
   - Pourquoi le conteneur redémarre-t-il en boucle ?

docker compose ps montre db en (healthy) mais api en « Restarting (3) » (8 redémarrages en 20 s). docker compose logs api répète : « psycopg.OperationalError: connection failed: connection to server at "127.0.0.1", port 5432 failed: Connection refused ».
Dans le conteneur api, localhost = l'API elle-même, où aucune base n'écoute. init_db() plante volontairement au démarrage si la base est injoignable, le processus s'arrête, et restart: unless-stopped le relance : l'erreur se reproduit à chaque fois, d'où la boucle. Réparation : remettre db dans DATABASE_URL.

2. **Modèle absent.** Supprimez `models/model.joblib` et redémarrez l'API. Quel code HTTP renvoie `/predict` ?

503 Service Unavailable (« Modèle introuvable »). L'API, elle, reste Up : /health répond avec "model_found": false. Réparation : réentraîner le modèle (docker run --rm -v ./data:/app/data:ro -v ./models:/app/models iris-api:v2 python train.py) puis docker compose restart api.

3. Pour les deux cas, notez la commande qui vous a permis de **trouver** le problème.

Mauvais hôte : docker compose ps (statut Restarting) puis docker compose logs api, qui donne la cause exacte (Connection refused sur 127.0.0.1).
Modèle absent : curl sur /predict (code 503) et /health ("model_found": false), confirmés par docker compose logs api (« POST /predict HTTP/1.1 503 Service Unavailable »).

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
