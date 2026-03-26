#!/bin/bash
source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base
export PATH=/home/crak/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

PANTHER=/mnt/c/Users/drkat/OneDrive/Desktop/oncopanther-pgx/oncopanther-pgx/panther

echo "=== 1. Reference genome files ==="
find $PANTHER/Reference_Genome -type f 2>/dev/null | head -20 || echo "No Reference_Genome dir"
ls -lh $PANTHER/Reference_Genome/ 2>/dev/null || echo "No Reference_Genome dir"

echo ""
echo "=== 2. Reference genome chromosomes (what contigs are in it?) ==="
REF=$(find $PANTHER/Reference_Genome -name "*.fa" -o -name "*.fasta" -o -name "*.fna" 2>/dev/null | head -1)
if [ -n "$REF" ]; then
    echo "Found: $REF"
    grep "^>" "$REF" | head -30
    CHRCOUNT=$(grep -c "^>" "$REF" 2>/dev/null || echo 0)
    echo "Total chromosomes/contigs: $CHRCOUNT"
else
    echo "No FASTA reference found"
fi

echo ""
echo "=== 3. Known sites for BQSR ==="
find $PANTHER/knownsites -type f 2>/dev/null | head -10 || echo "No knownsites dir"

echo ""
echo "=== 4. Input FASTQs (real or test?) ==="
ls -lh $PANTHER/Data/ 2>/dev/null | head -20

echo ""
echo "=== 5. CSVs / samplesheets ==="
ls -lh $PANTHER/CSVs/ 2>/dev/null

echo ""
echo "=== 6. Existing BAM/VCF outputs ==="
find $PANTHER/outdir -name "*.bam" 2>/dev/null | head -10
find $PANTHER/outdir -name "*.vcf.gz" 2>/dev/null | head -10

echo ""
echo "=== 7. params.json / nextflow.config key params ==="
grep -E 'genome|reference|aligner|assembly' $PANTHER/params.json 2>/dev/null | head -10
