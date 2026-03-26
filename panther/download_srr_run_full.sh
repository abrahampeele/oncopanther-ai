#!/bin/bash
# OncoPanther: Download real NA12878 SRR reads + run full pipeline
# SRR: ERR194147 (HiSeq 2500 2x150bp, ~30x WGS)
# Strategy: Download first 50M read pairs (≈10GB raw, ~3x WGS coverage)
#           sufficient for variant calling + PGx at major gene loci

DLOG=/home/crak/srr_download.log
exec > >(tee -a $DLOG) 2>&1

source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base

export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export NXF_JAVA_HOME=/home/crak/miniconda3
PANTHER='/mnt/c/Users/drkat/OneDrive/Desktop/oncopanther-pgx/oncopanther-pgx/panther'
export PATH=$JAVA_HOME/bin:/home/crak/miniconda3/bin:/home/crak/tools/Cyrius:$PANTHER:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export TERM=dumb

FASTQ_DIR=/home/crak/giab/NA12878/fastq
FASTA=/home/crak/references/GRCh38/GRCh38_full_analysis_set.fna
SPOTS=50000000   # 50M pairs = ~3x WGS coverage

echo "============================================================"
echo " OncoPanther-AI: SRR Download + Full Pipeline"
echo " Sample: ERR194147 (NA12878 / HG001 GIAB)"
echo " Target: ${SPOTS} read pairs (~3x WGS coverage)"
echo " Started: $(date)"
echo "============================================================"
echo ""

# ── STEP 1: Download real SRR reads ──────────────────────────────
echo "=== STEP 1: Downloading ${SPOTS} spots from ERR194147 ==="
echo "  (This streams directly from SRA cloud — no full 69GB download needed)"
echo "  Estimated download: ~10GB, ~30-60 min depending on network speed"
echo ""

mkdir -p $FASTQ_DIR $FASTQ_DIR/tmp
cd $FASTQ_DIR

# Remove old subsampled reads
rm -f NA12878_R1.fastq.gz NA12878_R2.fastq.gz ERR194147_1.fastq.gz ERR194147_2.fastq.gz

# Use fastq-dump (supports --maxSpotId) with --gzip for direct compressed output
# Note: fastq-dump is single-threaded but correctly supports spot limits
echo "  Using fastq-dump (single-threaded, outputs compressed directly)"
fastq-dump ERR194147 \
  --maxSpotId ${SPOTS} \
  --split-files \
  --gzip \
  --outdir $FASTQ_DIR \
  2>&1

if [ $? -ne 0 ]; then
  echo "ERROR: fastq-dump failed. Check network connection and SRA toolkit config."
  exit 1
fi

echo ""
echo "✓ Download complete: $(date)"
echo "  Files: $(ls -lh $FASTQ_DIR/ERR194147_*.fastq.gz 2>/dev/null | awk '{print $5, $9}')"

# ── STEP 2: Rename to expected filenames ─────────────────────────
echo ""
echo "=== STEP 2: Renaming output files ==="
mv -f ${FASTQ_DIR}/ERR194147_1.fastq.gz ${FASTQ_DIR}/NA12878_R1.fastq.gz
mv -f ${FASTQ_DIR}/ERR194147_2.fastq.gz ${FASTQ_DIR}/NA12878_R2.fastq.gz

READ_COUNT=$(zcat ${FASTQ_DIR}/NA12878_R1.fastq.gz | awk 'NR%4==1' | wc -l)
echo ""
echo "✓ Files ready: $(date)"
echo "  R1: $(ls -lh ${FASTQ_DIR}/NA12878_R1.fastq.gz | awk '{print $5}')"
echo "  R2: $(ls -lh ${FASTQ_DIR}/NA12878_R2.fastq.gz | awk '{print $5}')"
echo "  Reads: ${READ_COUNT} pairs"
echo ""

# ── STEP 3: Run full OncoPanther pipeline ────────────────────────
echo "=== STEP 3: Running full OncoPanther pipeline ==="
echo "  FASTQ -> BWA-MEM align -> GATK HaplotypeCaller -> PharmCAT PGx"
echo "  Reference: GRCh38"
echo ""

if [ ! -f "${FASTA}.bwt" ]; then
  echo "ERROR: BWA index not ready at ${FASTA}.bwt"
  exit 1
fi
echo "✓ BWA index ready"

cd $PANTHER

nextflow run main.nf \
  -c local.config \
  --fullmode \
  --input ./CSVs/3_samplesheetForAssembly_NA12878.csv \
  --reference $FASTA \
  --pgx \
  --pgxSources CPIC \
  --metaPatients ./CSVs/7_metaPatients_NA12878.csv \
  --metaYaml ./CSVs/7_metaPatients_NA12878.yml \
  --oncopantherLogo .oncopanther.png \
  --outdir ./outdir/NA12878 \
  -profile conda \
  -resume 2>&1

echo ""
echo "============================================================"
echo " FULL PIPELINE COMPLETE: $(date)"
echo " Outputs: $PANTHER/outdir/NA12878/"
echo "============================================================"
