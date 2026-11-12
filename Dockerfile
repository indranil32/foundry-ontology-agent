FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml README.md ./
COPY src ./src
RUN uv pip install --system --no-cache .
RUN useradd --create-home agent
USER agent
EXPOSE 8000
CMD ["uvicorn", "ontology_agent.server:app", "--host", "0.0.0.0", "--port", "8000"]
