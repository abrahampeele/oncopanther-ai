#!/bin/bash
# Persistent download of 500K read pairs from NA12878
# Uses nohup - survives shell exit
source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base
export PATH=/home/crak/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

OUTDIR=/home/crak/giab/NA12878/fastq
LOG=/home/crak/na12878_fastq.log
EBI_R1="ftp://ftp.sra.ebi.ac.uk/vol1/fastq/ERR194/ERR194147/ERR194147_1.fastq.gz"
EBI_R2="ftp://ftp.sra.ebi.ac.uk/vol1/fastq/ERR194/ERR194147/ERR194147_2.fastq.gz"
R1="$OUTDIR/NA12878_R1.fastq.gz"
R2="$OUTDIR/NA12878_R2.fastq.gz"

N_READS=500000       # 500K reads = 2M lines per file
N_LINES=$((N_READS * 4))

echo "=== NA12878 FASTQ Download ===" | tee $LOG
echo "Target: $N_READS read pairs per file" | tee -a $LOG
echo "" | tee -a $LOG

# Download R1
echo "Downloading R1 ($N_READS reads)..." | tee -a $LOG
echo "Started: $(date)" | tee -a $LOG
rm -f "$R1"
curl -s "$EBI_R1" 2>/dev/null | zcat 2>/dev/null | head -$N_LINES | gzip -1 > "$R1"
R1_LINES=$(zcat "$R1" 2>/dev/null | wc -l)
echo "R1 done: $R1_LINES lines = $((R1_LINES/4)) reads, $(du -sh $R1 | cut -f1)" | tee -a $LOG

# Download R2
echo "" | tee -a $LOG
echo "Downloading R2 ($N_READS reads)..." | tee -a $LOG
echo "Started: $(date)" | tee -a $LOG
rm -f "$R2"
curl -s "$EBI_R2" 2>/dev/null | zcat 2>/dev/null | head -$N_LINES | gzip -1 > "$R2"
R2_LINES=$(zcat "$R2" 2>/dev/null | wc -l)
echo "R2 done: $R2_LINES lines = $((R2_LINES/4)) reads, $(du -sh $R2 | cut -f1)" | tee -a $LOG

echo "" | tee -a $LOG
echo "=== All done at $(date) ===" | tee -a $LOG
ls -lh $OUTDIR/ | tee -a $LOG
