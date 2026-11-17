FROM python:3.12-slim

# Index PyTorch : CUDA 13.0 par défaut (GPU NVIDIA récents, dont RTX 50xx).
# Image CPU, plus légère (CI, machine sans GPU) :
#   docker build --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cpu .
ARG TORCH_INDEX=https://download.pytorch.org/whl/cu130
ARG TORCH_VERSION=2.14.1

# Les logs s'affichent immédiatement ; pas de fichiers .pyc dans l'image.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    SUBTITLER_HOST=0.0.0.0 \
    SUBTITLER_DATA_DIR=/app/data \
    HF_HOME=/app/cache/huggingface

# ffmpeg : extraction audio, incrustation et piste de sous-titres.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dépendances d'abord : ces couches (plusieurs Go pour torch CUDA) restent en
# cache tant que les requirements ne changent pas.
RUN pip install torch==${TORCH_VERSION} --index-url ${TORCH_INDEX}
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY subtitler/ subtitler/

# Utilisateur non-root, propriétaire des dossiers montés en volume.
RUN useradd --uid 1000 --create-home appuser \
    && mkdir -p /app/data /app/cache/huggingface \
    && chown -R appuser:appuser /app/data /app/cache
USER appuser

# Données (base SQLite, fichiers envoyés, résultats) et modèles téléchargés :
# à monter en volume pour qu'ils survivent à la recréation du conteneur.
VOLUME ["/app/data", "/app/cache/huggingface"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"]

CMD ["python", "-m", "subtitler"]
