#!/bin/bash
source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base
export PATH=/home/crak/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

FASTA=/home/crak/references/GRCh38/GRCh38_full_analysis_set.fna

echo "=== GRCh38 FASTA check ==="
ls -lh $FASTA
echo "Total sequences: $(grep -c '^>' $FASTA)"
echo ""
echo "Key PGx chromosomes:"
grep '^>' $FASTA | cut -d' ' -f1 | grep -E '^>(chr1|chr2|chr4|chr7|chr10|chr12|chr19|chr22|chrX)$'

echo ""
echo "=== samtools faidx ==="
if [ -f "${FASTA}.fai" ]; then
    echo "Already exists: ${FASTA}.fai"
else
    samtools faidx $FASTA && echo "Created: ${FASTA}.fai"
fi

echo ""
echo "=== samtools dict ==="
DICT="${FASTA%.fna}.dict"
if [ -f "$DICT" ]; then
    echo "Already exists: $DICT"
else
    samtools dict $FASTA -o $DICT && echo "Created: $DICT"
fi

echo ""
echo "=== BWA index (takes ~40-60 min) ==="
if [ -f "${FASTA}.bwt" ]; then
    echo "BWA index already exists!"
    ls -lh ${FASTA}.amb ${FASTA}.ann ${FASTA}.bwt ${FASTA}.pac ${FASTA}.sa
else
    echo "Starting BWA index at: $(date)"
    bwa index $FASTA
    echo "Finished BWA index at: $(date)"
    ls -lh ${FASTA}.amb ${FASTA}.ann ${FASTA}.bwt ${FASTA}.pac ${FASTA}.sa
fi

echo ""
echo "=== All reference files ==="
ls -lh /home/crak/references/GRCh38/
echo "=== DONE ==="
