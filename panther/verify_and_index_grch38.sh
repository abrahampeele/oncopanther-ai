#!/bin/bash
source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base
export PATH=/home/crak/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

FASTA=/home/crak/references/GRCh38/GRCh38_full_analysis_set.fna
REFDIR=/home/crak/references/GRCh38

echo "=== GRCh38 FASTA verification ==="
ls -lh $FASTA
echo ""
echo "Chromosomes in reference:"
grep "^>" $FASTA | cut -d' ' -f1 | head -30
echo ""
echo "Total sequences:"
grep -c "^>" $FASTA

echo ""
echo "=== Checking required tools ==="
which bwa && bwa 2>&1 | head -3 || echo "ERROR: bwa not found"
which samtools && samtools --version 2>&1 | head -1 || echo "ERROR: samtools not found"

echo ""
echo "=== Checking if BWA index already exists ==="
if [ -f "${FASTA}.bwt" ]; then
    echo "BWA index already exists!"
    ls -lh ${FASTA}.amb ${FASTA}.ann ${FASTA}.bwt ${FASTA}.pac ${FASTA}.sa 2>/dev/null
else
    echo "BWA index NOT found — starting indexing now..."
    echo "This will take ~40-60 minutes and needs ~5GB RAM"
    echo "Started at: $(date)"
    bwa index $FASTA 2>&1
    echo "Finished at: $(date)"
    echo ""
    echo "Index files:"
    ls -lh ${FASTA}.amb ${FASTA}.ann ${FASTA}.bwt ${FASTA}.pac ${FASTA}.sa
fi

echo ""
echo "=== Creating samtools FASTA index (.fai) ==="
if [ ! -f "${FASTA}.fai" ]; then
    samtools faidx $FASTA
    echo "Done: ${FASTA}.fai"
else
    echo "Already exists: ${FASTA}.fai"
fi

echo ""
echo "=== Creating sequence dictionary (.dict) ==="
DICT=${FASTA%.fna}.dict
if [ ! -f "$DICT" ]; then
    samtools dict $FASTA -o $DICT
    echo "Done: $DICT"
else
    echo "Already exists: $DICT"
fi

echo ""
echo "=== All done. Reference directory: ==="
ls -lh $REFDIR/
