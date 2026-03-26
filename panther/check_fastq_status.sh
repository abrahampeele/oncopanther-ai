#!/bin/bash
source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base
export PATH=/home/crak/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

FASTQDIR=/home/crak/giab/NA12878/fastq

echo "=== FASTQ files ==="
ls -lh $FASTQDIR/

echo ""
echo "=== R1 read count ==="
R1="$FASTQDIR/NA12878_R1.fastq.gz"
if [ -f "$R1" ]; then
    LINES=$(zcat "$R1" 2>/dev/null | wc -l)
    READS=$((LINES / 4))
    echo "Lines: $LINES"
    echo "Reads: $READS"
    echo "First read name: $(zcat $R1 2>/dev/null | head -1)"
else
    echo "R1 not found"
fi

echo ""
echo "=== Download process still running? ==="
ps aux | grep -E "curl|zcat|fast_na12878" | grep -v grep | awk '{print $11, $12}' | head -5

echo ""
echo "=== BWA index progress ==="
tail -3 /home/crak/bwa_index.log
