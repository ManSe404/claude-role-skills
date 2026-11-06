FROM python:3.12-slim
WORKDIR /srv/acme-orders
COPY . .
RUN pip install --no-cache-dir .
ENV ACME_DB_PATH=/data/acme.db
EXPOSE 8080
CMD ["python", "-m", "acme_orders", "serve", "--port", "8080"]
