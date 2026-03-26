#!/bin/bash
# Pre-process GIAB NA12878 VCF to remove non-standard PS=PATMAT field
# PharmCAT expects PS to be an integer, but GIAB uses "PATMAT" as phase set string
set -euo pipefail

source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base
export PATH=/usr/lib/jvm/java-17-openjdk-amd64/bin:/home/crak/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

GIAB_VCF=/home/crak/giab/NA12878/HG001_GRCh38_GIAB_highconf_CG-IllFB-IllGATKHC-Ion-10X-SOLID_CHROM1-X_v.3.3.2_highconf_PGandRTGphasetransfer.vcf.gz
CLEAN_VCF=/home/crak/giab/NA12878/HG001_GRCh38_GIAB_NA12878_pharmcat_ready.vcf.gz

echo "=== Stripping PS/IGT/IPS fields from GIAB VCF for PharmCAT compatibility ==="
echo "Input: $GIAB_VCF"
echo "Output: $CLEAN_VCF"
echo ""

# Remove FORMAT fields PS, IGT, IPS that cause PharmCAT parsing issues
# GT is already phased (0|1, 1|0, 1|1) so PS is not needed
bcftools annotate \
    -x FORMAT/PS,FORMAT/IGT,FORMAT/IPS \
    -O z \
    -o "$CLEAN_VCF" \
    "$GIAB_VCF"

echo "Indexing cleaned VCF..."
bcftools index -t "$CLEAN_VCF"

echo ""
echo "=== Verification ==="
echo "File size:"
ls -lh "$CLEAN_VCF"

echo ""
echo "FORMAT fields in cleaned VCF:"
bcftools view --header-only "$CLEAN_VCF" | grep "^##FORMAT"

echo ""
echo "First 2 data lines:"
bcftools view -H "$CLEAN_VCF" | head -2

echo ""
echo "=== Done! ==="
echo "Use this VCF in your pipeline: $CLEAN_VCF"
