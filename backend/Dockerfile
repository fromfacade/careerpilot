# Backend container for docker-compose (CI / non-Windows dev parity).
#
# NOTE: this Dockerfile has not been run on the primary dev machine for this
# project (Docker Desktop is not installed there — see
# docs/implementation-plan.md §0). The verified Phase 1 workflow is the
# native one described in README.md. This image is provided for later use
# and should be exercised in CI before being relied on.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
