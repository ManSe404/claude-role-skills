FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install .
EXPOSE 8081
CMD ["acme-worker"]
