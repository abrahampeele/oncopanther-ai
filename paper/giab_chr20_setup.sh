#!/usr/bin/env bash
# =============================================================================
# GIAB chr20 Validation Setup — OncoPanther-AI
# =============================================================================
# Downloads HG002 chr20 BAM (subset of 30x WGS), GRCh38 chr20 reference,
# and GIAB truth VCF restricted to chr20.
# Then generates the CSV inputs needed for the validation run.
#
# Runtime: ~30 min download on decent connection (~6GB total)
# Disk:    ~8GB working space needed
#
# Usage (inside Docker container or Linux host with samtools/wget):
#   bash giab_chr20_setup.sh [output_dir]
#
# Output structure:
#   $OUTDIR/
#     giab/
#       HG002_chr20.bam          <- chr20-only BAM (~300MB)
#       HG002_chr20.bam.bai
#       HG002_truth_chr20.vcf.gz <- truth VCF chr20 only (~5MB)
#       HG002_truth_chr20.vcf.gz.tbi
#       HG002_confident_chr20.bed
#     reference/
#       chr20.fa                 <- chr20-only reference (~65MB)
#       chr20.fa.fai
#       chr20.dict
#     inputs/
#       bam.csv                  <- input for --tovarcall
#       vcf.csv                  <- input for --validation (after calling)
# =============================================================================

set -euo pipefail

OUTDIR="${1:-/home/crak/demo_uploads/giab_validation}"
GIAB_BASE="https://ftp-trace.ncbi.nlm.nih.gov/giab/ftp"
THREADS="${THREADS:-8}"

echo "============================================"
echo " OncoPanther-AI — GIAB chr20 Setup"
echo " Output: $OUTDIR"
echo "============================================"
echo ""

mkdir -p "$OUTDIR/giab" "$OUTDIR/reference" "$OUTDIR/inputs"

# ── 1. Download HG002 chr20 BAM from GIAB (stream + extract chr20) ──────────
# GIAB provides GRCh38-aligned 35x Illumina HG002 BAM (publicly accessible)
HG002_BAM_URL="${GIAB_BASE}/data/AshkenazimTrio/HG002_NA24385_son/NIST_HiSeq_HG002_Crossplatform/NIST_HiSeqPE300x_HG002/alignment/HG002.hs37d5.300x.bam"

# For GRCh38 we use the NIST Illumina 2x150 35x coverage dataset
HG002_GRCh38_BAM_URL="${GIAB_BASE}/data/AshkenazimTrio/HG002_NA24385_son/NIST_IlluminaHiSeq300x_paired_end/NIST_HiSeqPE300x_HG002/alignment/HG002.NIST.GRCh38.bam"
HG002_GRCh38_BAI_URL="${HG002_GRCh38_BAM_URL}.bai"

CHR20_BAM="$OUTDIR/giab/HG002_chr20.bam"

if [ ! -f "$CHR20_BAM" ]; then
    echo "[1/5] Extracting HG002 chr20 BAM (streaming from NCBI)..."
    echo "      URL: $HG002_GRCh38_BAM_URL"
    echo "      This streams only the chr20 index region (~300MB)"
    samtools view -b \
        -@ "$THREADS" \
        --reference /dev/null \
        -X "$HG002_GRCh38_BAM_URL" "$HG002_GRCh38_BAI_URL" \
        chr20 \
        -o "$CHR20_BAM"
    samtools index "$CHR20_BAM"
    echo "      Done: $CHR20_BAM ($(du -sh "$CHR20_BAM" | cut -f1))"
else
    echo "[1/5] HG002 chr20 BAM already exists — skipping"
fi

# ── 2. Download GRCh38 chr20 reference ──────────────────────────────────────
CHR20_REF="$OUTDIR/reference/chr20.fa"

if [ ! -f "$CHR20_REF" ]; then
    echo "[2/5] Downloading GRCh38 chr20 reference from UCSC..."
    wget -q --show-progress \
        -O "$OUTDIR/reference/chr20.fa.gz" \
        "https://hgdownload.soe.ucsc.edu/goldenPath/hg38/chromosomes/chr20.fa.gz"
    gunzip "$OUTDIR/reference/chr20.fa.gz"
    samtools faidx "$CHR20_REF"
    samtools dict "$CHR20_REF" -o "$OUTDIR/reference/chr20.dict"
    echo "      Done: $CHR20_REF ($(du -sh "$CHR20_REF" | cut -f1))"
else
    echo "[2/5] chr20 reference already exists — skipping"
fi

# ── 3. Download GIAB HG002 truth VCF (NISTv4.2.1 GRCh38) ───────────────────
TRUTH_VCF_URL="${GIAB_BASE}/release/AshkenazimTrio/HG002_NA24385_son/NISTv4.2.1/GRCh38/HG002_GRCh38_1_22_v4.2.1_benchmark.vcf.gz"
TRUTH_BED_URL="${GIAB_BASE}/release/AshkenazimTrio/HG002_NA24385_son/NISTv4.2.1/GRCh38/HG002_GRCh38_1_22_v4.2.1_benchmark_noinconsistent.bed"
TRUTH_TBI_URL="${TRUTH_VCF_URL}.tbi"

TRUTH_VCF="$OUTDIR/giab/HG002_truth.vcf.gz"
TRUTH_VCF_CHR20="$OUTDIR/giab/HG002_truth_chr20.vcf.gz"

if [ ! -f "$TRUTH_VCF_CHR20" ]; then
    echo "[3/5] Downloading GIAB truth VCF (NISTv4.2.1 GRCh38)..."
    wget -q --show-progress -O "$TRUTH_VCF"     "$TRUTH_VCF_URL"
    wget -q --show-progress -O "${TRUTH_VCF}.tbi" "$TRUTH_TBI_URL"
    wget -q --show-progress -O "$OUTDIR/giab/HG002_confident.bed" "$TRUTH_BED_URL"

    echo "      Restricting truth set to chr20..."
    bcftools view -r chr20 -Oz -o "$TRUTH_VCF_CHR20" "$TRUTH_VCF"
    bcftools index --tbi "$TRUTH_VCF_CHR20"
    grep "^chr20" "$OUTDIR/giab/HG002_confident.bed" > "$OUTDIR/giab/HG002_confident_chr20.bed"
    echo "      Done: $(bcftools stats "$TRUTH_VCF_CHR20" | grep '^SN.*number of SNPs' | awk '{print $NF}') SNPs in truth chr20"
else
    echo "[3/5] chr20 truth VCF already exists — skipping"
fi

# ── 4. Known sites for BQSR (chr20 only) ────────────────────────────────────
# Using dbSNP chr20 from NCBI
DBSNP_URL="https://ftp.ncbi.nih.gov/snp/organisms/human_9606_b151_GRCh38p7/VCF/GATK/00-All.vcf.gz"
echo "[4/5] Note: BQSR requires dbSNP known sites."
echo "      For chr20-only testing, using GIAB truth as known sites is sufficient."
echo "      Full BQSR validation: provide --knownsite1 /path/to/dbsnp.vcf.gz"

# ── 5. Write input CSVs ──────────────────────────────────────────────────────
echo "[5/5] Writing input CSV files..."

# bam.csv — for variant calling step (--tovarcall)
cat > "$OUTDIR/inputs/bam.csv" << EOF
patient_id,BamFile
HG002_chr20,$CHR20_BAM
EOF

echo "      $OUTDIR/inputs/bam.csv"

# vcf.csv — for validation step (--validation, after calling)
# VCF will be at this path after running the pipeline
EXPECTED_VCF="$OUTDIR/variant_calling/HG002_chr20.vcf.gz"
cat > "$OUTDIR/inputs/vcf.csv" << EOF
patient_id,VcfFile
HG002_chr20,$EXPECTED_VCF
EOF

echo "      $OUTDIR/inputs/vcf.csv"

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "============================================"
echo " Setup complete!"
echo "============================================"
echo ""
echo "Files ready:"
echo "  BAM:       $CHR20_BAM"
echo "  Reference: $CHR20_REF"
echo "  Truth VCF: $TRUTH_VCF_CHR20"
echo "  Truth BED: $OUTDIR/giab/HG002_confident_chr20.bed"
echo ""
echo "Next steps:"
echo ""
echo "  STEP 1 — Run variant calling on chr20:"
echo "  nextflow run /opt/panther/main.nf \\"
echo "    --stepmode true \\"
echo "    --tovarcall $OUTDIR/inputs/bam.csv \\"
echo "    --reference $CHR20_REF \\"
echo "    --outdir $OUTDIR \\"
echo "    --region chr20 \\"
echo "    -profile docker"
echo ""
echo "  STEP 2 — Run GIAB validation:"
echo "  nextflow run /opt/panther/main.nf \\"
echo "    --validation true \\"
echo "    --tovarcall $OUTDIR/inputs/vcf.csv \\"
echo "    --reference $CHR20_REF \\"
echo "    --outdir $OUTDIR \\"
echo "    -profile docker"
echo ""
echo "  STEP 3 — Run runtime benchmark (separate run, full genome BAM needed):"
echo "  nextflow run /opt/panther/main.nf \\"
echo "    --benchmark true \\"
echo "    --tovarcall /path/to/full_genome_bam.csv \\"
echo "    --reference /path/to/GRCh38.fa \\"
echo "    --outdir $OUTDIR/benchmark \\"
echo "    -profile docker"
echo ""
