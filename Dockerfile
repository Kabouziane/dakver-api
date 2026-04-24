FROM python:3.12-slim-bookworm

# System deps — WeasyPrint a besoin de libpango + libcairo
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libffi8 \
    libjpeg62-turbo \
    libopenjp2-7 \
    libpng16-16 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dépendances Python en premier (layer cacheable)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code source
COPY . .

# Créer les dossiers attendus
RUN mkdir -p staticfiles media

EXPOSE 8000
