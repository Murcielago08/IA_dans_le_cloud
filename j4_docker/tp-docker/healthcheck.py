"""Utilisé par HEALTHCHECK : code de sortie 0 si l'API répond, 1 sinon.

L'image python:*-slim ne contient pas curl, d'où ce petit script en Python.
"""
import sys
import urllib.request

try:
    with urllib.request.urlopen("http://localhost:8000/health", timeout=3) as response:
        sys.exit(0 if response.status == 200 else 1)
except Exception:
    sys.exit(1)
