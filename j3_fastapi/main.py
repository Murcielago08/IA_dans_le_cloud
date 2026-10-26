import pickle
from pathlib import Path

import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel, Field

MODEL_PATH = Path(__file__).parent / "first_model.sav"
PRED_TO_STRING = ["Bonne santé", "Malade"]

with open(MODEL_PATH, "rb") as f:
    model = pickle.load(f)

app = FastAPI(title="Heart disease prediction API")


class Patient(BaseModel):
    age: int = Field(..., ge=0, le=120, examples=[54])
    sex: int = Field(..., ge=0, le=1, description="0 = femme, 1 = homme", examples=[1])


class Prediction(BaseModel):
    prediction: int
    label: str
    probability: float


@app.get("/")
def root():
    return {"message": "API de prédiction de maladie cardiaque. Voir /docs"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/predict", response_model=Prediction)
def predict(patient: Patient):
    X = pd.DataFrame([patient.model_dump()])
    pred = int(model.predict(X)[0])
    proba = float(model.predict_proba(X)[0][pred])
    return Prediction(prediction=pred, label=PRED_TO_STRING[pred], probability=proba)


@app.post("/predict_batch", response_model=list[Prediction])
def predict_batch(patients: list[Patient]):
    X = pd.DataFrame([p.model_dump() for p in patients])
    preds = model.predict(X)
    probas = model.predict_proba(X)
    return [
        Prediction(prediction=int(p), label=PRED_TO_STRING[int(p)], probability=float(pr[int(p)]))
        for p, pr in zip(preds, probas)
    ]
