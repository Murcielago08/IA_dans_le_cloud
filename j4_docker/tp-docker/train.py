"""Entraîne un classifieur sur data/iris.csv et le sauvegarde dans models/model.joblib.

Variables d'environnement :
- DATA_PATH   (défaut : data/iris.csv)
- MODEL_PATH  (défaut : models/model.joblib)
"""
import os
from pathlib import Path

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

DATA_PATH = Path(os.getenv("DATA_PATH", "data/iris.csv"))
MODEL_PATH = Path(os.getenv("MODEL_PATH", "models/model.joblib"))
FEATURES = ["sepal_length", "sepal_width", "petal_length", "petal_width"]

df = pd.read_csv(DATA_PATH)
X_train, X_test, y_train, y_test = train_test_split(
    df[FEATURES], df["species"], test_size=0.2, random_state=42, stratify=df["species"]
)

model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=500))
model.fit(X_train, y_train)
accuracy = model.score(X_test, y_test)

MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
joblib.dump(model, MODEL_PATH)

print(f"Modèle entraîné sur {len(X_train)} lignes — accuracy sur le jeu de test : {accuracy:.3f}")
print(f"Sauvegardé dans {MODEL_PATH}")
