#!/bin/bash
# Start BWA indexing of GRCh38 in background
source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base
export PATH=/home/crak/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

LOG=/home/crak/bwa_index.log
FASTA=/home/crak/references/GRCh38/GRCh38_full_analysis_set.fna

echo "=== Verifying FASTA ===" | tee $LOG
ls -lh $FASTA >> $LOG 2>&1
grep -c "^>" $FASTA >> $LOG 2>&1
echo "Chromosomes:" >> $LOG
grep "^>" $FASTA | cut -d' ' -f1 | head -30 >> $LOG 2>&1

echo "" >> $LOG
echo "=== samtools faidx ===" | tee -a $LOG
samtools faidx $FASTA >> $LOG 2>&1 && echo "faidx done" | tee -a $LOG

echo "" >> $LOG
echo "=== samtools dict ===" | tee -a $LOG
DICT="${FASTA%.fna}.dict"
[ -f "$DICT" ] || samtools dict $FASTA -o $DICT >> $LOG 2>&1
echo "dict done" | tee -a $LOG

echo "" >> $LOG
echo "=== BWA index - started at $(date) ===" | tee -a $LOG
bwa index $FASTA >> $LOG 2>&1
echo "=== BWA index - finished at $(date) ===" | tee -a $LOG

ls -lh /home/crak/references/GRCh38/ | tee -a $LOG
