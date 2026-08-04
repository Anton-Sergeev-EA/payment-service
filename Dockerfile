FROM python:3.14-slim

WORKDIR /app

# Install dependencies.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source.
COPY src/ ./src/

# Create data directory.
RUN mkdir -p /data

# Expose port.
EXPOSE 8080

# Run the application.
CMD ["python", "-m", "src.main"]
