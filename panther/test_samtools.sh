#!/bin/bash
source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base
export PATH=/home/crak/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export TERM=dumb

# Kill any stuck samtools processes first
pkill -f "samtools faidx" 2>/dev/null || true
pkill -f "run_bwa_index" 2>/dev/null || true
sleep 2

echo "=== samtools version ==="
samtools --version 2>&1 | head -3

echo ""
echo "=== Test faidx on small file ==="
printf '>chr1\nACGTACGT\n>chr2\nTTTTAAAA\n' > /tmp/test.fa
samtools faidx /tmp/test.fa 2>/dev/null
echo "Exit: $?"
cat /tmp/test.fa.fai 2>/dev/null && echo "faidx works!" || echo "faidx FAILED"

echo ""
echo "=== Now try on actual GRCh38 (first 10MB only as test) ==="
FASTA=/home/crak/references/GRCh38/GRCh38_full_analysis_set.fna

# Check if .fai already exists from stuck run
if [ -f "${FASTA}.fai" ]; then
    echo ".fai already exists:"
    wc -l "${FASTA}.fai"
else
    echo "Running samtools faidx on full reference..."
    timeout 120 samtools faidx $FASTA 2>&1
    echo "Exit: $?"
    [ -f "${FASTA}.fai" ] && echo "Created .fai! Lines: $(wc -l < ${FASTA}.fai)" || echo "FAILED to create .fai"
fi
