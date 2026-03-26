#!/bin/bash
# Run PGx pipeline on NA12878 GIAB benchmark sample
set -euo pipefail

source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base

export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export NXF_JAVA_HOME=/home/crak/miniconda3
PANTHER=/mnt/c/Users/drkat/OneDrive/Desktop/oncopanther-pgx/oncopanther-pgx/panther
export PATH=$JAVA_HOME/bin:/home/crak/miniconda3/bin:$PANTHER:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PYTHONPATH=$PANTHER:${PYTHONPATH:-}

echo "=== OncoPanther-PGx: NA12878 Benchmark Run ==="
echo "Java: $(java -version 2>&1 | head -1)"
echo "Nextflow: $(nextflow -version 2>&1 | grep version | head -1)"
echo "bcftools: $(bcftools --version 2>&1 | head -1)"
echo ""

cd $PANTHER

nextflow run main.nf \
  -c local.config \
  --stepmode \
  --exec pgx \
  --pgxVcf ./CSVs/8_samplesheetPgx_NA12878.csv \
  --pgxSources CPIC \
  --metaPatients ./CSVs/7_metaPatients_NA12878.csv \
  --metaYaml ./CSVs/7_metaPatients_NA12878.yml \
  --oncopantherLogo .oncopanther.png \
  -profile conda \
  -resume 2>&1

echo ""
echo "=== Run complete ==="
