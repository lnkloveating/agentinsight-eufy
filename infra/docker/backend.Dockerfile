FROM python:3.12-slim
WORKDIR /app
COPY src/backend/pyproject.toml ./
COPY src/backend/app ./app
RUN pip install --no-cache-dir .
EXPOSE 8000
CMD ["python", "-m", "app.main"]
