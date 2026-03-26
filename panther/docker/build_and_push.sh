#!/bin/bash
# OncoPanther-AI — Build and Push Docker Image
# Run this on any Linux/Mac machine with Docker installed
# Usage: bash docker/build_and_push.sh [--push]

set -e

IMAGE="oncopanther/oncopanther-ai"
TAG="${1:-latest}"
PUSH="${2:-}"

cd "$(dirname "$0")/.."   # Go to panther/ root

echo "=============================================="
echo "  OncoPanther-AI Docker Build"
echo "  Image: ${IMAGE}:${TAG}"
echo "=============================================="

# Build
echo "[1/3] Building Docker image..."
docker build \
    --tag "${IMAGE}:${TAG}" \
    --tag "${IMAGE}:latest" \
    --file Dockerfile \
    --platform linux/amd64 \
    --progress=plain \
    .

echo ""
echo "[2/3] Image built successfully!"
docker images "${IMAGE}" --format "  {{.Repository}}:{{.Tag}}  {{.Size}}"

# Push (if requested)
if [ "$PUSH" == "--push" ] || [ "$TAG" == "--push" ]; then
    echo ""
    echo "[3/3] Pushing to DockerHub..."
    echo "      (Make sure you're logged in: docker login)"
    docker push "${IMAGE}:${TAG}"
    docker push "${IMAGE}:latest"
    echo "✅ Pushed! Partner can now run:"
    echo "   docker run -d -p 8501:8501 -p 8000:8000 \\"
    echo "     -v oncopanther-refs:/refs \\"
    echo "     -v oncopanther-data:/data \\"
    echo "     ${IMAGE}:latest"
else
    echo ""
    echo "[3/3] To push to DockerHub, run:"
    echo "   docker login"
    echo "   bash docker/build_and_push.sh ${TAG} --push"
fi

echo ""
echo "✅ Done!"
