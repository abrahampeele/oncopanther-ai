#!/bin/bash
source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export NXF_JAVA_HOME=/home/crak/miniconda3
PANTHER=/mnt/c/Users/drkat/OneDrive/Desktop/oncopanther-pgx/oncopanther-pgx/panther
export PATH=$JAVA_HOME/bin:/home/crak/miniconda3/bin:$PANTHER:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PYTHONPATH=$PANTHER:$PYTHONPATH

echo '=== which bcftools ==='
which bcftools
bcftools --version 2>&1 | head -2

echo ''
echo '=== bcftools view test on NA12878 VCF ==='
bcftools view --header-only /home/crak/giab/NA12878/HG001_GRCh38_GIAB_highconf_CG-IllFB-IllGATKHC-Ion-10X-SOLID_CHROM1-X_v.3.3.2_highconf_PGandRTGphasetransfer.vcf.gz 2>&1 | head -5
echo "Exit: $?"

echo ''
echo '=== VCF files ==='
ls -lh /home/crak/giab/NA12878/
