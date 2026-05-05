FROM python:3.11-slim

# Install system dependencies for GDAL, geospatial libraries, and Spanish locale
RUN apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    g++ \
    locales \
    && rm -rf /var/lib/apt/lists/*

# Generate Spanish locale
RUN sed -i '/es_ES.UTF-8/s/^# //g' /etc/locale.gen && \
    locale-gen es_ES.UTF-8

# Set locale environment variables
ENV LANG=es_ES.UTF-8
ENV LANGUAGE=es_ES:es
ENV LC_ALL=es_ES.UTF-8

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (NOT .env, keys/, or temp data!)
COPY main.py .
COPY run_monthly.py .
COPY src/ ./src/

# Create necessary directories
RUN mkdir -p temp_data temp_outputs AOIs

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Default: run with automatic month/year calculation
# Override with: docker run -e MODE=manual -e ANIO=2025 -e MES=4
ENV MODE=auto
ENV ANIO=2025
ENV MES=1

# Run script: auto mode runs main.py without args (fallback to previous month), manual mode uses params
CMD if [ "$MODE" = "manual" ]; then \
        python main.py --anio ${ANIO} --mes ${MES}; \
    else \
        python main.py; \
    fi
