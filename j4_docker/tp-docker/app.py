"""API de prédiction Iris.

- GET  /health       : état de l'API (utilisé par le HEALTHCHECK)
- POST /predict      : prédit l'espèce d'une fleur, et enregistre la prédiction si une base est configurée
- GET  /predictions  : les dernières prédictions enregistrées dans PostgreSQL

Configuration par variables d'environnement :
- MODEL_PATH    chemin du modèle entraîné (défaut : models/model.joblib)
- DATABASE_URL  URL PostgreSQL, ex. postgresql://app:secret@db:5432/app (absente = pas de base)
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

import joblib
import pandas as pd
import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

MODEL_PATH = Path(os.getenv("MODEL_PATH", "models/model.joblib"))
DATABASE_URL = os.getenv("DATABASE_URL")

_model = None


def get_model():
    global _model
    if _model is None:
        if not MODEL_PATH.exists():
            raise HTTPException(
                status_code=503,
                detail=f"Modèle introuvable : {MODEL_PATH}. Entraînez-le d'abord avec train.py.",
            )
        _model = joblib.load(MODEL_PATH)
    return _model


def init_db():
    """Crée la table au démarrage. Plante si la base est injoignable : c'est voulu."""
    if not DATABASE_URL:
        print("DATABASE_URL absente : les prédictions ne seront pas enregistrées.")
        return
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS predictions (
                id           SERIAL PRIMARY KEY,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
                sepal_length REAL,
                sepal_width  REAL,
                petal_length REAL,
                petal_width  REAL,
                species      TEXT
            )
            """
        )
    print("Connexion à PostgreSQL OK, table predictions prête.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="API Iris", lifespan=lifespan)


class Fleur(BaseModel):
    sepal_length: float
    sepal_width: float
    petal_length: float
    petal_width: float


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model_found": MODEL_PATH.exists(),
        "database_configured": bool(DATABASE_URL),
        "hostname": os.uname().nodename,
    }


@app.post("/predict")
def predict(fleur: Fleur):
    model = get_model()
    features = fleur.model_dump()
    species = str(model.predict(pd.DataFrame([features]))[0])

    if DATABASE_URL:
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute(
                "INSERT INTO predictions (sepal_length, sepal_width, petal_length, petal_width, species)"
                " VALUES (%s, %s, %s, %s, %s)",
                (*features.values(), species),
            )
    return {"species": species, "saved": bool(DATABASE_URL)}


@app.get("/predictions")
def predictions(limit: int = 10):
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="Pas de base configurée (DATABASE_URL absente).")
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            "SELECT created_at, species FROM predictions ORDER BY id DESC LIMIT %s", (limit,)
        ).fetchall()
    return [{"created_at": r[0].isoformat(), "species": r[1]} for r in rows]
