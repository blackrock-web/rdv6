# ROADAI Enterprise | Hugging Face Optimized Dockerfile
# Optimized for HF Spaces (Port 7860 + Non-Root User)

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (OpenCV & Video Processing requirements)
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Setup non-root user for Hugging Face (UID 1000)
# This prevents permission issues with uploads/outputs
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:${PATH}"

# Install Python requirements
COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Copy all project code
COPY --chown=user:user . .

# Create persistent directories
RUN mkdir -p uploads outputs/reports config models/custom models/runtime

# Hugging Face Spaces default port
ENV PORT=7860
EXPOSE 7860

# Start the FastAPI engine
# Pointing to 7860 specifically for HF
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port 7860 --workers 1"]
