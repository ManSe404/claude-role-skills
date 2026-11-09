# Acme Logistics

Parcel delivery for businesses in and around Novi Sad. This repository holds the software behind it.

## What is here

- `src/Acme.Api/`: the HTTP API.
- `src/Acme.Logistics/`: shipments, billing and the code they share.
- `web/`: the web app used at the counters.
- `worker/`: the tracking worker, which follows parcels with the carrier.
- `docs/briefs/`: briefs for what comes next.

## Running it

Publish the API once, then start everything with Docker Compose:

    dotnet publish src/Acme.Api -c Release -o src/Acme.Api/publish
    docker compose up --build

The API listens on port 8080, the web app on 4200 and the tracking worker on 8081.
