FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=10001:10001 basheco ./basheco
COPY --chown=10001:10001 sql ./sql
COPY --chown=10001:10001 tests ./tests
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "basheco.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
