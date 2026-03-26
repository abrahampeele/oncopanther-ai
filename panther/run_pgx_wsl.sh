#!/bin/bash
# OncoPanther PGx Pipeline — WSL Run Script
# Run from WSL bash: bash run_pgx_wsl.sh

source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base

# Use system Java 17 (standard version string, required by PharmCAT)
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64

# Use conda's Java for Nextflow itself
export NXF_JAVA_HOME=/home/crak/miniconda3

PANTHER=/mnt/c/Users/drkat/OneDrive/Desktop/oncopanther-pgx/oncopanther-pgx/panther

# Add panther dir to PATH (for pharmcat_vcf_preprocessor, pharmcat_pipeline)
export PATH=$JAVA_HOME/bin:/home/crak/miniconda3/bin:$PANTHER:$PATH

# Add panther dir to PYTHONPATH (for pcat module import)
export PYTHONPATH=$PANTHER:$PYTHONPATH

echo "=== Environment ==="
echo "Java:      $(java -version 2>&1 | head -1)"
echo "Nextflow:  $(nextflow -version 2>&1 | grep version | head -1)"
echo "bcftools:  $(bcftools --version | head -1)"
echo "PharmCAT:  $(pharmcat_pipeline --version 2>&1 | head -1)"
echo "==================="

cd $PANTHER

nextflow run main.nf \
    -c local.config \
    --stepmode \
    --exec pgx \
    --pgxVcf ./CSVs/8_samplesheetPgx.csv \
    --pgxSources CPIC \
    --metaPatients ./CSVs/7_metaPatients.csv \
    --metaYaml ./CSVs/7_metaPatients.yml \
    --oncopantherLogo .oncopanther.png \
    -profile conda \
    -resume

echo ""
echo "=== PGx PDF Reports ==="
ls -lh outdir/Reporting/PGx/*.pdf 2>/dev/null || echo "No PDFs found"
