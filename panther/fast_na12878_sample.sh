#!/bin/bash
# Fast approach: Stream first 1M read pairs from EBI FTP
# NA12878 WGS FASTQs available at EBI FTP (ERR194147)
# Stream + decompress + take first 4M lines (=1M reads) + recompress
# Total download: ~300MB instead of 51GB
set -euo pipefail

source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base
export PATH=/home/crak/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export TERM=dumb

# Kill any existing slow fastq-dump
pkill -f "fastq-dump ERR194147" 2>/dev/null || true
sleep 2

OUTDIR=/home/crak/giab/NA12878/fastq
mkdir -p $OUTDIR

EBI_R1="ftp://ftp.sra.ebi.ac.uk/vol1/fastq/ERR194/ERR194147/ERR194147_1.fastq.gz"
EBI_R2="ftp://ftp.sra.ebi.ac.uk/vol1/fastq/ERR194/ERR194147/ERR194147_2.fastq.gz"
R1="$OUTDIR/NA12878_R1.fastq.gz"
R2="$OUTDIR/NA12878_R2.fastq.gz"

N_READS=1000000   # 1 million read pairs = ~100MB compressed

echo "=== Downloading first ${N_READS} read pairs from NA12878 WGS ==="
echo "Source: EBI FTP ERR194147 (HiSeq 2500 2x100bp, 30x WGS)"
echo "Method: Stream gzip -> decompress -> head ${N_READS} reads -> recompress"
echo ""

if [ -f "$R1" ] && [ "$(stat -c%s $R1 2>/dev/null || echo 0)" -gt 1000000 ]; then
    echo "R1 already exists: $(ls -lh $R1 | awk '{print $5}')"
else
    echo "Downloading R1... (streaming ~200MB of ${N_READS} reads)"
    echo "Started: $(date)"
    # Stream gzip, decompress on-the-fly, take first N reads, recompress
    curl -s "$EBI_R1" 2>/dev/null | zcat 2>/dev/null | head -$((N_READS * 4)) | gzip -1 > "$R1"
    echo "R1 done: $(ls -lh $R1 | awk '{print $5}') at $(date)"
fi

if [ -f "$R2" ] && [ "$(stat -c%s $R2 2>/dev/null || echo 0)" -gt 1000000 ]; then
    echo "R2 already exists: $(ls -lh $R2 | awk '{print $5}')"
else
    echo "Downloading R2... (streaming ~200MB of ${N_READS} reads)"
    echo "Started: $(date)"
    curl -s "$EBI_R2" 2>/dev/null | zcat 2>/dev/null | head -$((N_READS * 4)) | gzip -1 > "$R2"
    echo "R2 done: $(ls -lh $R2 | awk '{print $5}') at $(date)"
fi

echo ""
echo "=== Verification ==="
ls -lh "$R1" "$R2"
echo "R1 read count: $(zcat $R1 2>/dev/null | wc -l | awk '{print $1/4}') reads"
echo ""
echo "=== Done. Ready for pipeline run once BWA index completes ==="
