FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt \
    && useradd --create-home bot
COPY --chown=bot:bot . .
RUN mkdir -p data && chown bot:bot data
USER bot
CMD ["python", "-m", "bot.main"]
