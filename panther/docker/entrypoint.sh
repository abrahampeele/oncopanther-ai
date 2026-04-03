#!/bin/bash
set -euo pipefail

REFS_DIR="${REFS_DIR:-/refs}"
STATUS_FILE="${REFS_DIR}/.setup_complete"
PANTHER_DIR="/app/panther"

echo "======================================================"
echo "  OncoPanther-AI v2.0.0"
echo "  Clinical Genomics Pipeline"
echo "  $(date)"
echo "======================================================"

if [ ! -f "$STATUS_FILE" ]; then
    echo ""
    echo "  FIRST RUN DETECTED"
    echo "  Reference data not found at ${REFS_DIR}"
    echo "  Starting automatic setup..."
    echo ""

    python3 "${PANTHER_DIR}/docker/setup_progress_app.py" &
    SETUP_UI_PID=$!

    echo "  Setup progress: http://localhost:8501"
    echo "  Downloading references (~40 GB)..."
    echo "  This takes 4-8 hours on first run only"
    echo ""

    bash "${PANTHER_DIR}/docker/setup_refs.sh" 2>&1
    kill "$SETUP_UI_PID" 2>/dev/null || true

    echo ""
    echo "  SETUP COMPLETE - Starting OncoPanther..."
    echo ""
fi

GRCh38_FA="${REFS_DIR}/GRCh38/GRCh38_full_analysis_set.fna"
VEP_CACHE="${REFS_DIR}/vep_cache"
CLINVAR="${REFS_DIR}/clinvar/clinvar.vcf.gz"

cat > /tmp/runtime_params.json << EOF
{
  "reference":   "${GRCh38_FA}",
  "cachedir":    "${VEP_CACHE}",
  "clinvar":     "${CLINVAR}",
  "outdir":      "/data/output",
  "pgxRefGenome": "${GRCh38_FA}"
}
EOF

export ONCOPANTHER_REFS="$REFS_DIR"
export ONCOPANTHER_FASTA="$GRCh38_FA"
export ONCOPANTHER_VEP_CACHE="$VEP_CACHE"
export ONCOPANTHER_CLINVAR="$CLINVAR"

# Fix VEP cache directory structure
mkdir -p "${REFS_DIR}/vep_cache/homo_sapiens" 2>/dev/null || true
if [ -d "${REFS_DIR}/vep_cache/114_GRCh38" ] && [ ! -L "${REFS_DIR}/vep_cache/homo_sapiens/114_GRCh38" ]; then
  ln -sf "${REFS_DIR}/vep_cache/114_GRCh38" "${REFS_DIR}/vep_cache/homo_sapiens/114_GRCh38"
fi
if [ -d "/home/crak/.vep/114_GRCh38" ] && [ ! -L "/home/crak/.vep/homo_sapiens/114_GRCh38" ]; then
  mkdir -p /home/crak/.vep/homo_sapiens
  ln -sf /home/crak/.vep/114_GRCh38 /home/crak/.vep/homo_sapiens/114_GRCh38
fi

echo "[$(date)] Starting Ollama LLM server..."
ollama serve > /tmp/ollama.log 2>&1 &
OLLAMA_PID=$!
sleep 3
echo "[$(date)] Ollama ready (model: llama3.2:3b)"

echo "[$(date)] Starting FastAPI on port 8000..."
cd "$PANTHER_DIR"
uvicorn demo_app.api:app \
    --host 0.0.0.0 --port 8000 \
    --log-level warning &
API_PID=$!

echo "[$(date)] Starting Streamlit on port 8501..."
streamlit run "${PANTHER_DIR}/demo_app/app.py" \
    --server.port 8501 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --server.maxUploadSize 2048 \
    --browser.gatherUsageStats false &
ST_PID=$!

sleep 3

echo ""
echo "======================================================"
echo "  OncoPanther-AI is READY!"
echo ""
echo "  Web App:    http://localhost:8501"
echo "  REST API:   http://localhost:8000"
echo "  API Docs:   http://localhost:8000/docs"
echo ""
echo "  References: ${REFS_DIR}"
echo "  Output:     /data/output"
echo "======================================================"

wait $ST_PID $API_PID $OLLAMA_PID
