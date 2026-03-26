#!/bin/bash
# Stream NA12878 WGS BAM from EBI for PGx gene regions only
# No full download needed — samtools streams only requested regions
# BAM is GRCh37/hg19 aligned; we extract FASTQs and realign to GRCh38

source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base
export PATH=/home/crak/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export TERM=dumb

OUTDIR=/home/crak/giab/NA12878/fastq
mkdir -p $OUTDIR

# EBI SRA BAM for NA12878 (GRCh37/hg19 aligned)
BAM_URL="http://ftp.sra.ebi.ac.uk/vol1/run/ERR194/ERR194147/NA12878_S1.bam"
BAI_URL="${BAM_URL}.bai"

echo "=== Step 0: Check BAM access ==="
curl -s --head "$BAM_URL" 2>/dev/null | grep -E "HTTP|Content-Length|Last-Modified" | head -4
curl -s --head "$BAI_URL" 2>/dev/null | grep -E "HTTP|Content-Length" | head -2

echo ""
echo "=== Step 1: Download BAM index (.bai) — small file ==="
BAI_LOCAL="$OUTDIR/NA12878_S1.bam.bai"
if [ -f "$BAI_LOCAL" ]; then
    echo "BAI already downloaded"
else
    curl -L -o "$BAI_LOCAL" "$BAI_URL" 2>&1
    ls -lh "$BAI_LOCAL"
fi

echo ""
echo "=== Step 2: Stream PGx gene regions (GRCh37 coords) ==="
echo "Note: BAM uses GRCh37 chromosome names (1, 2, 4... not chr1, chr2...)"

# PGx gene regions in GRCh37 (hg19) coordinates
PGX_REGIONS="1:97543299-97543600 2:234668879-234669179 4:87551756-87551956 4:89051164-89051414 7:99756775-99756975 12:21394819-21394919 19:40974338-40975338 22:42522501-42522701"

echo "Streaming regions: $PGX_REGIONS"
echo "Started at: $(date)"

# Stream and sort by name for paired FASTQ extraction
samtools view -b "$BAM_URL" $PGX_REGIONS 2>/dev/null \
  | samtools sort -n -o "$OUTDIR/NA12878_pgx_regions.bam" \
  && echo "BAM extraction done: $(ls -lh $OUTDIR/NA12878_pgx_regions.bam)"

echo "Finished at: $(date)"

echo ""
echo "=== Step 3: Convert to FASTQ ==="
if [ -f "$OUTDIR/NA12878_pgx_regions.bam" ]; then
    samtools fastq "$OUTDIR/NA12878_pgx_regions.bam" \
        -1 "$OUTDIR/NA12878_R1.fastq.gz" \
        -2 "$OUTDIR/NA12878_R2.fastq.gz" \
        -0 /dev/null -s /dev/null \
        -n 2>/dev/null
    echo "FASTQ files:"
    ls -lh "$OUTDIR/"
fi
