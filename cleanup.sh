#!/bin/bash
##############################################################################
# OncoPanther-AI Cleanup Script
# Removes temporary/cached files to reduce folder size for distribution
# Keeps only essential pipeline code + PharmCAT
##############################################################################

echo "OncoPanther-AI Cleanup"
echo "======================"

PANTHER_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PANTHER_DIR"

echo ""
echo "Current size: $(du -sh . 2>/dev/null | cut -f1)"
echo ""

# 1. Nextflow work directory (biggest — conda caches + intermediate files)
echo "[1/7] Removing work/ directory (Nextflow cache + conda envs)..."
rm -rf work/
echo "      Done"

# 2. Test output results
echo "[2/7] Removing outdir/ (test pipeline results)..."
rm -rf outdir/
echo "      Done"

# 3. Test reference genome
echo "[3/7] Removing test reference genome files..."
rm -rf Reference_Genome/
rm -f reference.fna.bgz reference.fna.bgz.gzi
echo "      Done"

# 4. Old branding files
echo "[4/7] Removing old DelMoro branding..."
rm -f .delmoro.png .DelMoroWlc.png
echo "      Done"

# 5. Nextflow log files
echo "[5/7] Removing Nextflow log files..."
rm -f .nextflow.log*
echo "      Done"

# 6. Temp scripts
echo "[6/7] Removing temp scripts..."
rm -f run_pgx.sh
echo "      Done"

# 7. Nextflow cache
echo "[7/7] Cleaning Nextflow metadata..."
rm -rf .nextflow/
echo "      Done"

echo ""
echo "======================"
echo "Cleaned size: $(du -sh . 2>/dev/null | cut -f1)"
echo ""
echo "Kept:"
echo "  ✔ Pipeline code (main.nf, modules/, subworkflows/)"
echo "  ✔ Config files (nextflow.config, conf/)"
echo "  ✔ CSV templates (CSVs/)"
echo "  ✔ PharmCAT (pharmcat.jar, pharmcat_pipeline, pcat/)"
echo "  ✔ Test data (Data/) — delete manually if not needed"
echo "  ✔ Known sites (knownsites/) — delete manually if not needed"
echo "  ✔ Setup script (setup_oncopanther.sh)"
echo "  ✔ Logo (.oncopanther.png)"
echo ""
echo "To also remove test data (saves ~31MB more):"
echo "  rm -rf Data/ knownsites/"
