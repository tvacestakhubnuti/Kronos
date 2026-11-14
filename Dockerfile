FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HOME=/app/state/hf-cache
WORKDIR /app

RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
COPY bot/requirements.txt bot/requirements.txt
RUN pip install -r bot/requirements.txt

COPY model/ model/
COPY bot/ bot/

RUN useradd -m botuser && mkdir -p /app/state && chown -R botuser /app
USER botuser

CMD ["python", "-m", "bot.main"]
