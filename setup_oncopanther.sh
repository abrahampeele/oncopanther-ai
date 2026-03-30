#!/bin/bash
##############################################################################
# OncoPanther-AI Pipeline - One-Click Setup Script
# By SecuAI | Authors: Abraham Peele, Kesava Mullati,
#                       Vuyyuru Kesavi Hima Bindhu, Rayidi Sri Sai Chinmai
#
# Run this on a fresh Linux / WSL machine:
#   bash setup_oncopanther.sh
#
# Prerequisites: Ubuntu 20.04+ / Debian-based Linux
##############################################################################

set -e
echo ""
echo "   ██████╗ ███╗   ██╗ ██████╗ ██████╗ ██████╗  █████╗ ███╗   ██╗████████╗██╗  ██╗███████╗██████╗ "
echo "  ██╔═══██╗████╗  ██║██╔════╝██╔═══██╗██╔══██╗██╔══██╗████╗  ██║╚══██╔══╝██║  ██║██╔════╝██╔══██╗"
echo "  ██║   ██║██╔██╗ ██║██║     ██║   ██║██████╔╝███████║██╔██╗ ██║   ██║   ███████║█████╗  ██████╔╝"
echo "  ██║   ██║██║╚██╗██║██║     ██║   ██║██╔═══╝ ██╔══██║██║╚██╗██║   ██║   ██╔══██║██╔══╝  ██╔══██╗"
echo "  ╚██████╔╝██║ ╚████║╚██████╗╚██████╔╝██║     ██║  ██║██║ ╚████║   ██║   ██║  ██║███████╗██║  ██║"
echo "   ╚═════╝ ╚═╝  ╚═══╝ ╚═════╝ ╚═════╝ ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═══╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝"
echo ""
echo "  ═══════════════════════════════════════════════════════════════"
echo "    OncoPanther-AI Setup Script | SecuAI"
echo "  ═══════════════════════════════════════════════════════════════"
echo ""

PANTHER_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "[INFO] Pipeline directory: $PANTHER_DIR"
echo ""

##############################################################################
# Step 1: System dependencies
##############################################################################
echo "╔════════════════════════════════════════╗"
echo "║  Step 1/6: System Dependencies         ║"
echo "╚════════════════════════════════════════╝"

sudo apt-get update -qq
sudo apt-get install -y -qq openjdk-17-jdk curl wget git unzip

export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
echo "[OK] Java 17 installed: $(java -version 2>&1 | head -1)"

##############################################################################
# Step 2: Miniconda (if not already installed)
##############################################################################
echo ""
echo "╔════════════════════════════════════════╗"
echo "║  Step 2/6: Miniconda                    ║"
echo "╚════════════════════════════════════════╝"

if command -v conda &> /dev/null; then
    echo "[OK] Conda already installed: $(conda --version)"
else
    echo "[INSTALLING] Miniconda..."
    wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /tmp/miniconda.sh
    bash /tmp/miniconda.sh -b -p $HOME/miniconda3
    rm /tmp/miniconda.sh
    source $HOME/miniconda3/etc/profile.d/conda.sh
    conda init bash
    echo "[OK] Miniconda installed"
fi

# Source conda
CONDA_DIR=$(conda info --base 2>/dev/null || echo "$HOME/miniconda3")
source "$CONDA_DIR/etc/profile.d/conda.sh"

##############################################################################
# Step 3: Create oncopanther conda environment
##############################################################################
echo ""
echo "╔════════════════════════════════════════╗"
echo "║  Step 3/6: Conda Environment            ║"
echo "╚════════════════════════════════════════╝"

if conda env list | grep -q "oncopanther"; then
    echo "[OK] oncopanther conda env already exists"
else
    echo "[CREATING] oncopanther conda environment..."
    conda create -n oncopanther -y -q \
        -c bioconda -c conda-forge \
        nextflow \
        bcftools=1.21 \
        samtools \
        pandas \
        numpy \
        matplotlib \
        seaborn
    echo "[OK] oncopanther env created"
fi

conda activate oncopanther

# Remove conda's bundled Java if it conflicts
if [ -f "$CONDA_DIR/envs/oncopanther/bin/java" ]; then
    CONDA_JAVA_VER=$($CONDA_DIR/envs/oncopanther/bin/java -version 2>&1 | head -1)
    if echo "$CONDA_JAVA_VER" | grep -q "internal"; then
        echo "[FIX] Removing conda's broken Java (internal build)..."
        conda remove -n oncopanther openjdk --force -y -q 2>/dev/null || true
    fi
fi

echo "[OK] bcftools: $(bcftools --version | head -1)"

##############################################################################
# Step 4: Install Nextflow (if not in conda)
##############################################################################
echo ""
echo "╔════════════════════════════════════════╗"
echo "║  Step 4/6: Nextflow                     ║"
echo "╚════════════════════════════════════════╝"

if command -v nextflow &> /dev/null; then
    echo "[OK] Nextflow already installed: $(nextflow -version 2>/dev/null | grep version | head -1)"
else
    echo "[INSTALLING] Nextflow..."
    curl -s https://get.nextflow.io | bash
    sudo mv nextflow /usr/local/bin/
    echo "[OK] Nextflow installed"
fi

##############################################################################
# Step 5: Install PharmCAT
##############################################################################
echo ""
echo "╔════════════════════════════════════════╗"
echo "║  Step 5/6: PharmCAT                     ║"
echo "╚════════════════════════════════════════╝"

if [ -f "$PANTHER_DIR/pharmcat_pipeline" ]; then
    echo "[OK] PharmCAT already present in pipeline directory"
else
    echo "[INSTALLING] PharmCAT..."
    cd "$PANTHER_DIR"
    curl -fsSL https://get.pharmcat.org | bash
    echo "[OK] PharmCAT installed"
fi

# Install PharmCAT Python dependencies
pip install -q colorama 2>/dev/null || true
echo "[OK] PharmCAT dependencies installed"

# Install PDF report dependencies
pip install -q reportlab qrcode 2>/dev/null || true
echo "[OK] PDF reporting dependencies installed"

##############################################################################
# Step 6: Configure ~/.bashrc
##############################################################################
echo ""
echo "╔════════════════════════════════════════╗"
echo "║  Step 6/6: Shell Configuration          ║"
echo "╚════════════════════════════════════════╝"

CONDA_DIR=$(conda info --base)

if grep -q "OncoPanther-AI Pipeline Setup" ~/.bashrc 2>/dev/null; then
    echo "[OK] ~/.bashrc already configured"
else
    cat >> ~/.bashrc << BASHEOF

# === OncoPanther-AI Pipeline Setup ===
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH=\$JAVA_HOME/bin:${PANTHER_DIR}:\$PATH
source ${CONDA_DIR}/etc/profile.d/conda.sh
conda activate oncopanther
BASHEOF
    echo "[OK] ~/.bashrc updated"
fi

##############################################################################
# Verification
##############################################################################
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  OncoPanther-AI Setup Complete!"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "  Java:       $(java -version 2>&1 | head -1)"
echo "  Nextflow:   $(nextflow -version 2>/dev/null | grep version | head -1)"
echo "  Conda env:  oncopanther"
echo "  bcftools:   $(bcftools --version | head -1)"
echo "  PharmCAT:   $(which pharmcat_pipeline)"
echo "  Pipeline:   $PANTHER_DIR"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  To run the pipeline:"
echo ""
echo "  # Open a new terminal, then:"
echo "  cd $PANTHER_DIR"
echo ""
echo "  # Full mode (FASTQ to VCF):"
echo "  nextflow run main.nf --fullmode --input ./CSVs/1_samplesheetForRawQC.csv \\"
echo "      --reference /path/to/hg38.fa -profile conda"
echo ""
echo "  # PGx only:"
echo "  nextflow run main.nf --stepmode --exec pgx \\"
echo "      --pgxVcf ./CSVs/8_samplesheetPgx.csv \\"
echo "      --pgxSources CPIC \\"
echo "      --metaPatients ./CSVs/7_metaPatients.csv \\"
echo "      --metaYaml ./CSVs/7_metaPatients.yml \\"
echo "      --oncopantherLogo .oncopanther.png \\"
echo "      -profile conda"
echo ""
echo "  # Help:"
echo "  nextflow run main.nf --stepmode --exec help"
echo "═══════════════════════════════════════════════════════════════"
