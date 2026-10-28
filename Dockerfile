FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static
COPY templates ./templates
COPY run.py .

ENV DEMO_MODE=false
ENV PORT=8765
ENV PYTHONUNBUFFERED=1

EXPOSE 8765

CMD ["python", "run.py"]
