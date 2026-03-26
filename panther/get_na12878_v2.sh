#!/bin/bash
# Get NA12878 real WGS reads — using fastq-dump with spot limit
source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base
export PATH=/home/crak/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export TERM=dumb

OUTDIR=/home/crak/giab/NA12878/fastq
mkdir -p $OUTDIR

echo "=== Tool versions ==="
fastq-dump --version 2>&1 | head -2
fasterq-dump --version 2>&1 | head -2

echo ""
echo "=== Approach: fastq-dump with --maxSpotId ==="
echo "Downloading first 3,000,000 read pairs from ERR194147"
echo "These are real NA12878 WGS reads (HiSeq 2500, 100bp PE)"
echo "Started: $(date)"

# fastq-dump supports --maxSpotId for subsetting
fastq-dump ERR194147 \
    --split-files \
    --maxSpotId 3000000 \
    --gzip \
    -O "$OUTDIR" \
    --outdir "$OUTDIR" 2>&1

echo "Finished: $(date)"

# Rename to standard R1/R2
[ -f "$OUTDIR/ERR194147_1.fastq.gz" ] && mv "$OUTDIR/ERR194147_1.fastq.gz" "$OUTDIR/NA12878_R1.fastq.gz"
[ -f "$OUTDIR/ERR194147_2.fastq.gz" ] && mv "$OUTDIR/ERR194147_2.fastq.gz" "$OUTDIR/NA12878_R2.fastq.gz"

echo ""
echo "=== Result ==="
ls -lh "$OUTDIR/"
echo "Read count R1:"
zcat "$OUTDIR/NA12878_R1.fastq.gz" 2>/dev/null | wc -l | awk '{print $1/4}' || echo "failed"
