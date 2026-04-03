#!/bin/bash
set -e

IMAGE="abpeele/oncopanther-ai"

echo "======================================"
echo "  OncoPanther-AI -> DockerHub Push"
echo "  Image: ${IMAGE}:latest"
echo "======================================"

echo ""
if ! docker image inspect "${IMAGE}:latest" > /dev/null 2>&1; then
    echo "ERROR: Image ${IMAGE}:latest not found locally."
    echo "Build it first: bash docker/build_and_push.sh"
    exit 1
fi

docker images "${IMAGE}" --format "  Found: {{.Repository}}:{{.Tag}}  ({{.Size}})"

echo ""
echo "Pushing ${IMAGE}:latest to DockerHub..."
docker push "${IMAGE}:latest"

echo ""
echo "SUCCESS: Push complete!"
