#!/bin/bash
source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base
export PATH=/home/crak/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

echo "=== Installing Cyrius dependencies ==="
mamba install -y -c conda-forge -c bioconda pysam scipy numpy 2>&1

echo ""
echo "=== Installing Cyrius via pip (from GitHub) ==="
pip install git+https://github.com/Illumina/Cyrius.git 2>&1

echo ""
echo "=== Verifying Cyrius ==="
which cyrius
cyrius --version 2>&1 || cyrius -h 2>&1 | head -5
echo "Done. Exit: $?"
