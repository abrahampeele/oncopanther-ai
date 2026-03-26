#!/bin/bash
# Push OncoPanther-AI to DockerHub
# Usage: bash docker/push_to_dockerhub.sh
# Run AFTER: docker login

set -e
IMAGE="oncopanther/oncopanther-ai"

echo "======================================"
echo "  OncoPanther-AI -> DockerHub Push"
echo "  Image: ${IMAGE}:latest"
echo "  Size:  ~7.2 GB"
echo "======================================"
echo ""

# Verify image exists locally
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
echo ""
echo "Partners can now deploy with:"
echo ""
echo "  docker run -d -p 8501:8501 -p 8000:8000 \\"
echo "    -v oncopanther-refs:/refs \\"
echo "    -v oncopanther-data:/data \\"
echo "    ${IMAGE}:latest"
echo ""
echo "  Then open: http://localhost:8501"
