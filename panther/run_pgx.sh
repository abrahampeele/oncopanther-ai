#!/bin/bash
# Initialize conda
source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base

# Set Java 17 for PharmCAT
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH=$JAVA_HOME/bin:/mnt/d/oncopanther-pgx/panther:$PATH

cd /mnt/d/oncopanther-pgx/panther

echo "=== Environment Check ==="
echo "conda: $(conda --version)"
echo "Java: $(java -version 2>&1 | head -1)"
echo "PharmCAT: $(which pharmcat_pipeline)"
echo "Nextflow: $(which nextflow)"
echo "========================="

nextflow run main.nf \
    --stepmode \
    --exec pgx \
    --pgxVcf ./CSVs/8_samplesheetPgx.csv \
    --pgxSources CPIC \
    --metaPatients ./CSVs/7_metaPatients.csv \
    --metaYaml ./CSVs/7_metaPatients.yml \
    --oncopantherLogo .oncopanther.png \
    -profile conda \
    -resume
