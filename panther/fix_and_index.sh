#!/bin/bash
source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base
export PATH=/home/crak/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export TERM=dumb
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64

FASTA=/home/crak/references/GRCh38/GRCh38_full_analysis_set.fna
LOG=/home/crak/bwa_index.log

# Kill any stuck samtools dict/faidx processes
pkill -f "samtools dict" 2>/dev/null || true
pkill -f "bwa_index_background" 2>/dev/null || true
sleep 2
echo "Killed any stuck processes" | tee $LOG

# Use system samtools 1.13 for dict (avoids ncurses conflict)
DICT="${FASTA%.fna}.dict"
echo "" | tee -a $LOG
echo "=== Creating .dict using system samtools ===" | tee -a $LOG
if [ -s "$DICT" ]; then
    echo ".dict already exists and non-empty" | tee -a $LOG
else
    rm -f "$DICT"
    /usr/bin/samtools dict $FASTA -o $DICT 2>&1 | tee -a $LOG
    echo "dict lines: $(wc -l < $DICT)" | tee -a $LOG
fi

# BWA index - this is the long step
echo "" | tee -a $LOG
echo "=== BWA index started at $(date) ===" | tee -a $LOG
if [ -f "${FASTA}.bwt" ] && [ -s "${FASTA}.bwt" ]; then
    echo "BWA index already exists! Size: $(du -sh ${FASTA}.bwt | cut -f1)" | tee -a $LOG
else
    bwa index $FASTA 2>&1 | tee -a $LOG
    echo "=== BWA index done at $(date) ===" | tee -a $LOG
fi

echo "" | tee -a $LOG
echo "=== Final reference directory ===" | tee -a $LOG
ls -lh /home/crak/references/GRCh38/ | tee -a $LOG
echo "DONE" | tee -a $LOG
