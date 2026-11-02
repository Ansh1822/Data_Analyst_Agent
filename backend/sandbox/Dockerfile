# Optional hardened sandbox:  docker build -t analyst-sandbox backend/sandbox
FROM python:3.11-slim
RUN pip install --no-cache-dir pandas numpy matplotlib seaborn scipy duckdb
RUN useradd -m runner
USER runner
WORKDIR /work
