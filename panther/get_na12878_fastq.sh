#!/bin/bash
# Get NA12878 FASTQ — practical approach with multiple fallbacks
source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base
export PATH=/home/crak/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export TERM=dumb

OUTDIR=/home/crak/giab/NA12878/fastq
mkdir -p $OUTDIR
BAM_URL="http://ftp.sra.ebi.ac.uk/vol1/run/ERR194/ERR194147/NA12878_S1.bam"

echo "=== Trying to find BAI for remote streaming ==="
for BAI_URL in \
    "${BAM_URL}.bai" \
    "${BAM_URL%.bam}.bai" \
    "${BAM_URL%.bam}.bam.csi" \
    "http://ftp.sra.ebi.ac.uk/vol1/run/ERR194/ERR194147/NA12878_S1.bai"; do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" --head "$BAI_URL")
    SIZE=$(curl -s --head "$BAI_URL" 2>/dev/null | grep Content-Length | awk '{print $2}' | tr -d '\r')
    echo "  $BAI_URL -> HTTP $STATUS (size: $SIZE)"
    if [ "$STATUS" = "200" ] && [ "${SIZE:-0}" -gt 1000 ] 2>/dev/null; then
        echo "  FOUND valid BAI!"
        curl -L -o "$OUTDIR/NA12878_S1.bam.bai" "$BAI_URL"
        break
    fi
done

echo ""
if [ -f "$OUTDIR/NA12878_S1.bam.bai" ] && [ "$(stat -c%s $OUTDIR/NA12878_S1.bam.bai 2>/dev/null || echo 0)" -gt 1000 ]; then
    echo "=== Streaming PGx regions from remote BAM ==="
    # PGx regions in GRCh37 coords (this BAM is hg19-aligned)
    samtools view -h "$BAM_URL##idx##$OUTDIR/NA12878_S1.bam.bai" \
        1:97543299-97543600 \
        2:234668879-234669179 \
        4:87551756-87702156 \
        7:99756775-99756975 \
        12:21394819-21394919 \
        19:40974338-40975338 \
        22:42522501-42922701 \
        -b 2>/dev/null | samtools sort -n | samtools fastq - \
        -1 "$OUTDIR/NA12878_R1.fastq.gz" \
        -2 "$OUTDIR/NA12878_R2.fastq.gz" \
        -0 /dev/null -s /dev/null -n 2>/dev/null
    echo "Done. Files:"
    ls -lh $OUTDIR/
else
    echo "=== Fallback: fasterq-dump (first 2M read pairs, ~200MB) ==="
    echo "This gives real reads from NA12878 to test the full pipeline"
    echo "Coverage will be sparse (~0.06x whole genome) but adequate for pipeline test"
    echo "Started: $(date)"
    fasterq-dump ERR194147 \
        --outdir "$OUTDIR" \
        --temp /tmp \
        --threads 8 \
        --maxSpotId 2000000 \
        --split-files \
        --progress 2>&1
    echo "Finished: $(date)"
    # Compress
    gzip -1 "$OUTDIR/ERR194147_1.fastq" 2>/dev/null && mv "$OUTDIR/ERR194147_1.fastq.gz" "$OUTDIR/NA12878_R1.fastq.gz"
    gzip -1 "$OUTDIR/ERR194147_2.fastq" 2>/dev/null && mv "$OUTDIR/ERR194147_2.fastq.gz" "$OUTDIR/NA12878_R2.fastq.gz"
    echo "Files:"
    ls -lh $OUTDIR/
fi
