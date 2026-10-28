FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock \
    && useradd --uid 10001 --create-home clara \
    && mkdir -p /app/data && chown -R clara:clara /app
COPY --chown=clara:clara app ./app
USER clara
EXPOSE 8000
# Single worker and single instance: SQLite, IMAP consumption and the calendar lock depend on it.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --no-access-log"]
