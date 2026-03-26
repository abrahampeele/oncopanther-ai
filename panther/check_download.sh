#!/bin/bash
echo "=== GRCh38 download status ==="
FILE=/home/crak/references/GRCh38/GRCh38_full_analysis_set.fna.gz
FASTA=/home/crak/references/GRCh38/GRCh38_full_analysis_set.fna

if [ -f "$FASTA" ]; then
    SIZE=$(du -sh "$FASTA" | cut -f1)
    echo "Decompressed FASTA ready: $SIZE"
elif [ -f "$FILE" ]; then
    SIZE=$(du -sh "$FILE" | cut -f1)
    echo "Still downloading/decompressing: $SIZE so far"
else
    echo "Download not started or failed"
fi

echo ""
echo "=== Download process running? ==="
ps aux | grep -E "curl|gunzip|download_grch38" | grep -v grep | awk '{print $11, $12}' | head -5

echo ""
echo "=== Last lines of download log ==="
grep -E "[0-9]+\.[0-9]+%" /home/crak/grch38_download.log 2>/dev/null | tail -1 || tail -3 /home/crak/grch38_download.log 2>/dev/null
