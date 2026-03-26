#!/bin/bash
source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base
export PATH=/usr/lib/jvm/java-17-openjdk-amd64/bin:/home/crak/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

WORKDIR=/mnt/c/Users/drkat/OneDrive/Desktop/oncopanther-pgx/oncopanther-pgx/panther/work/b9/4cb29e210e52bcd26f9ced72143a0a

echo "=== Work dir files ==="
ls -lh $WORKDIR/

echo ""
echo "=== Preprocessed VCF - lines around PATMAT ==="
bcftools view $WORKDIR/NA12878.preprocessed.vcf.bgz 2>&1 | grep "PATMAT" | head -5
echo "Exit: $?"

echo ""
echo "=== VCF FORMAT fields in preprocessed ==="
bcftools view --header-only $WORKDIR/NA12878.preprocessed.vcf.bgz 2>&1 | grep "^##FORMAT"

echo ""
echo "=== First 3 data lines ==="
bcftools view -H $WORKDIR/NA12878.preprocessed.vcf.bgz 2>&1 | head -3
