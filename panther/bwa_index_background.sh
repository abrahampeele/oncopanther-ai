#!/bin/bash
source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base
export PATH=/home/crak/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export TERM=dumb

FASTA=/home/crak/references/GRCh38/GRCh38_full_analysis_set.fna
LOG=/home/crak/bwa_index.log

echo "=== BWA GRCh38 index — started at $(date) ===" | tee $LOG

# Create .dict if missing
DICT="${FASTA%.fna}.dict"
if [ ! -f "$DICT" ]; then
    echo "Creating sequence dictionary..." | tee -a $LOG
    samtools dict $FASTA -o $DICT 2>&1 | tee -a $LOG
    echo "dict done" | tee -a $LOG
else
    echo "dict already exists" | tee -a $LOG
fi

# Run BWA index
echo "" | tee -a $LOG
echo "=== Running: bwa index $FASTA ===" | tee -a $LOG
echo "Started: $(date)" | tee -a $LOG
bwa index $FASTA 2>&1 | tee -a $LOG
echo "=== BWA index complete at $(date) ===" | tee -a $LOG

echo "" | tee -a $LOG
echo "=== Index files created: ===" | tee -a $LOG
ls -lh ${FASTA}.amb ${FASTA}.ann ${FASTA}.bwt ${FASTA}.pac ${FASTA}.sa 2>&1 | tee -a $LOG
echo "DONE" | tee -a $LOG
