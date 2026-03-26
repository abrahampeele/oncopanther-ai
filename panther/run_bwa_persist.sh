#!/bin/bash
# Run BWA index with persistent background (survives shell exit)
source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base
export PATH=/home/crak/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export TERM=dumb

FASTA=/home/crak/references/GRCh38/GRCh38_full_analysis_set.fna
LOG=/home/crak/bwa_index.log

# Clean up any empty .pac from previous failed run
[ -f "${FASTA}.pac" ] && [ ! -s "${FASTA}.pac" ] && rm -f "${FASTA}.pac"

echo "Starting BWA index at $(date)" | tee $LOG

# Run BWA index in foreground (called by the outer nohup)
bwa index "$FASTA" >> "$LOG" 2>&1
EXIT=$?

echo "BWA index finished at $(date) with exit code $EXIT" | tee -a $LOG
ls -lh "${FASTA}"* >> $LOG 2>&1
