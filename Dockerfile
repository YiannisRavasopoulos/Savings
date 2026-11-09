# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Athens

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Chart.js, pinned to an exact version, fetched at build time so the running
# app needs no internet access.
# The checksum makes the build fail if the download isn't exactly this file.
ADD --chmod=644 --checksum=sha256:2f27bcf471b2d69dd78494f6e2172fb28470eb843820e2f96bb85d39f9618d30 \
    https://cdn.jsdelivr.net/npm/chart.js@4.5.0/dist/chart.umd.min.js \
    /app/app/static/vendor/chart.umd.min.js

COPY . .

# 8080: the app (LAN). 8091: the admin app (published to this PC's localhost only).
EXPOSE 8080 8091
CMD ["python", "-m", "app.serve"]
