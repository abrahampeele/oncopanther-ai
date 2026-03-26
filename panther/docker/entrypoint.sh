#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# OncoPanther-AI Docker Entrypoint
#
# Flow:
#   1. Check if reference data exists
#   2. If NOT → start setup web page + download refs in background
#   3. If YES → start full pipeline + Streamlit immediately
# ═══════════════════════════════════════════════════════════════════════════

REFS_DIR="${REFS_DIR:-/refs}"
STATUS_FILE="${REFS_DIR}/.setup_complete"
PANTHER_DIR="/app/panther"

echo "======================================================"
echo "  OncoPanther-AI v1.0.0"
echo "  Clinical Genomics Pipeline"
echo "  $(date)"
echo "======================================================"

# ── Check if first run ────────────────────────────────────────────────────────
if [ ! -f "$STATUS_FILE" ]; then
    echo ""
    echo "  🔧 FIRST RUN DETECTED"
    echo "  Reference data not found at ${REFS_DIR}"
    echo "  Starting automatic setup..."
    echo ""

    # Start setup progress web page on port 8501
    python3 "${PANTHER_DIR}/docker/setup_progress_app.py" &
    SETUP_UI_PID=$!

    echo "  🌐 Setup progress: http://localhost:8501"
    echo "  ⏳ Downloading references (~40 GB)..."
    echo "  📧 This takes 4-8 hours on first run only"
    echo ""

    # Run setup in foreground (progress shown in web UI)
    bash "${PANTHER_DIR}/docker/setup_refs.sh" 2>&1

    # Kill setup UI
    kill $SETUP_UI_PID 2>/dev/null

    echo ""
    echo "  ✅ SETUP COMPLETE — Starting OncoPanther..."
    echo ""
fi

# ── Update nextflow params to use Docker volume refs ─────────────────────────
GRCh38_FA="${REFS_DIR}/GRCh38/GRCh38_full_analysis_set.fna"
VEP_CACHE="${REFS_DIR}/vep_cache"
CLINVAR="${REFS_DIR}/clinvar/clinvar.vcf.gz"

# Write runtime params override
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

# ── Start FastAPI REST API ────────────────────────────────────────────────────
echo "[$(date)] Starting FastAPI on port 8000..."
cd "$PANTHER_DIR"
uvicorn demo_app.api:app \
    --host 0.0.0.0 --port 8000 \
    --log-level warning &
API_PID=$!

# ── Start Streamlit App ───────────────────────────────────────────────────────
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
echo "  ✅ OncoPanther-AI is READY!"
echo ""
echo "  🌐 Web App:    http://localhost:8501"
echo "  🔌 REST API:   http://localhost:8000"
echo "  📖 API Docs:   http://localhost:8000/docs"
echo ""
echo "  📁 References: ${REFS_DIR}"
echo "  📁 Output:     /data/output"
echo "======================================================"

wait $ST_PID $API_PID
