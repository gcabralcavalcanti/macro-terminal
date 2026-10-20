# Runs the tests and builds the page from the committed data; no API key or network needed.
#   docker build -t macro-terminal .
#   docker run --rm -v "$PWD/output:/app/output" macro-terminal
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["sh", "-c", "python -m pytest -q && python demo.py --no-open"]
