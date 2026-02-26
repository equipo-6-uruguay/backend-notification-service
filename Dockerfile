FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar dependencias de produccion antes de copiar el codigo
# para aprovechar la cache de capas de Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el codigo fuente
COPY . .

# Crear usuario de sistema sin privilegios de root [DT-05 / US-INFRA-01]
# El proceso NO corre como root, reduciendo la superficie de ataque
RUN addgroup --system appgroup \
    && adduser --system --ingroup appgroup --no-create-home appuser \
    && chown -R appuser:appgroup /app \
    && chmod +x /app/entrypoint.sh

USER appuser

EXPOSE 8000

CMD ["/app/entrypoint.sh"]
