FROM python:3.12-slim

# Les print s'affichent immédiatement dans les logs
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Dépendances d'abord : cette couche reste en cache tant que requirements.txt ne change pas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Utilisateur non-root
RUN useradd --uid 1000 --create-home appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "healthcheck.py"]

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
