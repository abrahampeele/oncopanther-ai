#!/bin/bash
set -e

IMAGE="abpeele/oncopanther-ai"
TAG="${1:-latest}"
PUSH="${2:-}"

cd "$(dirname "$0")/.."

echo "=============================================="
echo "  OncoPanther-AI Docker Build"
echo "  Image: ${IMAGE}:${TAG}"
echo "=============================================="

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

if [ "$PUSH" == "--push" ] || [ "$TAG" == "--push" ]; then
    echo ""
    echo "[3/3] Pushing to DockerHub..."
    docker push "${IMAGE}:${TAG}"
    docker push "${IMAGE}:latest"
else
    echo ""
    echo "[3/3] To push to DockerHub, run:"
    echo "   docker login"
    echo "   bash docker/build_and_push.sh ${TAG} --push"
fi

echo ""
echo "Done."
