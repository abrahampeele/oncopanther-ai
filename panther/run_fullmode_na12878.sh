#!/bin/bash
# OncoPanther-AI: Full pipeline run on NA12878 real WGS data
# FASTQ -> Alignment (BWA) -> Variant Calling (GATK HC) -> PGx (PharmCAT + Cyrius)
# Note: BQSR skipped for test run (500K reads = ~0.015x coverage, not meaningful for recalibration)
set -euo pipefail

source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export NXF_JAVA_HOME=/home/crak/miniconda3
PANTHER=/mnt/c/Users/drkat/OneDrive/Desktop/oncopanther-pgx/oncopanther-pgx/panther
export PATH=$JAVA_HOME/bin:/home/crak/miniconda3/bin:/home/crak/tools/Cyrius:$PANTHER:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PYTHONPATH=$PANTHER:${PYTHONPATH:-}
export TERM=dumb

echo "============================================"
echo " OncoPanther-AI: NA12878 Full Pipeline Run"
echo "============================================"
echo "Java:      $(java -version 2>&1 | head -1)"
echo "Nextflow:  $(nextflow -version 2>&1 | grep version | head -1)"
echo "BWA:       $(bwa 2>&1 | grep Version | head -1)"
echo "bcftools:  $(bcftools --version 2>&1 | head -1)"
echo "Cyrius:    $(cyrius --version 2>/dev/null || cyrius -h 2>&1 | head -1 || echo 'via wrapper')"
echo ""

# Check prerequisites
FASTA=/home/crak/references/GRCh38/GRCh38_full_analysis_set.fna
if [ ! -f "${FASTA}.bwt" ]; then
    echo "ERROR: BWA index not ready yet! Check: tail -f /home/crak/bwa_index.log"
    exit 1
fi
if [ ! -f "/home/crak/giab/NA12878/fastq/NA12878_R1.fastq.gz" ]; then
    echo "ERROR: NA12878 FASTQs not ready! Check: tail -f /home/crak/na12878_fastq.log"
    exit 1
fi
echo "✓ BWA index ready"
echo "✓ FASTQs ready: $(ls -lh /home/crak/giab/NA12878/fastq/NA12878_R?.fastq.gz | awk '{print $5, $9}')"
echo ""

cd $PANTHER

# Clean previous NA12878 outputs (don't use -resume for fresh run)
echo "=== Starting Nextflow full pipeline ==="
nextflow run main.nf \
  -c local.config \
  --fullmode \
  --input ./CSVs/3_samplesheetForAssembly_NA12878.csv \
  --reference $FASTA \
  --pgx \
  --pgxSources CPIC \
  --cyp2d6 \
  --pgxBam ./CSVs/9_samplesheetPgxBam_NA12878.csv \
  --metaPatients ./CSVs/7_metaPatients_NA12878.csv \
  --metaYaml ./CSVs/7_metaPatients_NA12878.yml \
  --oncopantherLogo .oncopanther.png \
  -profile conda \
  --outdir ./outdir/NA12878 \
  -resume 2>&1

echo ""
echo "=== Run complete ==="
echo "Outputs: $PANTHER/outdir/NA12878/"
