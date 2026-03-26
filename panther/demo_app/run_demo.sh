#!/bin/bash
source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base
export TERM=dumb
echo "Starting OncoPanther-AI dashboard at http://localhost:8501"
streamlit run "/mnt/c/Users/drkat/OneDrive/Desktop/oncopanther-pgx/oncopanther-pgx/panther/demo_app/app.py" \
  --server.port 8501 \
  --server.address 0.0.0.0 \
  --server.headless true \
  --server.maxUploadSize 2048 \
  --browser.gatherUsageStats false
