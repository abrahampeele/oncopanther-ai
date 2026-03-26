#!/bin/bash
# Download NA12878 WGS reads for PGx-relevant chromosomes only
# Strategy: Download specific chromosome BAMs from GIAB FTP, extract FASTQs
# PGx genes span: chr1 (DPYD), chr2 (UGT1A1), chr4 (CYP2C9/19/8, ABCG2, NUDT15),
#                 chr7 (CYP3A5/4), chr10, chr12 (SLCO1B1), chr16 (NAT2),
#                 chr19 (CYP2B6, TPMT), chr22 (CYP2D6), chrX (G6PD)
#
# GIAB HiSeq 2500 2x150bp BAMs are on NCBI FTP in merged format
# We use samtools view to slice just the PGx gene regions
set -euo pipefail

source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base
export PATH=/home/crak/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export TERM=dumb

OUTDIR=/home/crak/giab/NA12878/fastq
mkdir -p $OUTDIR

# GIAB NA12878 HiSeq 2500 2x150 merged WGS BAM (GRCh38 aligned)
# Available at NCBI FTP - this is the primary analysis BAM
GIAB_BAM="https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/data/NA12878/Genome_in_a_Bottle_v0.2/2014-10-14_Justin_BioProject_PRJNA200694_backup_Illumina_2x150bpTruSeq_HiSeqX/Combined/HG001.hs37d5.300x.bam"

# PGx gene regions on GRCh38 (chr-prefixed)
PGX_REGIONS=(
    "chr1:97079924-99383206"    # DPYD
    "chr2:233756340-233756670"  # UGT1A1
    "chr4:88028853-88069940"    # CYP2C8
    "chr4:88183951-88247547"    # CYP2C9
    "chr4:68743018-68904245"    # ABCG2
    "chr4:143132254-143133802"  # NUDT15
    "chr7:99245224-99267809"    # CYP3A5
    "chr7:99354579-99381820"    # CYP3A4
    "chr12:21130872-21239312"   # SLCO1B1
    "chr16:28339218-28429214"   # NAT2 (note: this region varies)
    "chr19:40993412-41128646"   # CYP2B6
    "chr19:18061911-18101998"   # TPMT
    "chr22:42126499-42933656"   # CYP2D6 (wide region for SV calling)
    "chrX:154531392-154589338"  # G6PD
)

echo "=== NA12878 FASTQ Download for PGx chromosomes ==="
echo "Strategy: Download targeted BAM regions from GIAB FTP via samtools view"
echo ""
echo "Note: Full WGS BAM is ~100GB — we download only PGx regions"
echo "GIAB BAM: GRCh37-aligned (will realign to GRCh38)"
echo ""

# Try to slice from streaming BAM (no full download needed)
echo "Testing streaming access to GIAB BAM..."
samtools view -H "$GIAB_BAM" 2>/dev/null | head -5 || {
    echo "Direct streaming failed. Using alternative: EBI 1000 genomes CRAM"

    # Alternative: 1000 Genomes Project CRAM for NA12878 (GRCh38)
    EBI_CRAM="http://ftp.1000genomes.ebi.ac.uk/vol1/ftp/data_collections/1000_genomes_project/data/CEU/NA12878/alignment/NA12878.alt_bwamem_GRCh38DH.20150706.CEU.low_coverage.cram"
    echo "Trying EBI 1000G CRAM: $EBI_CRAM"
    samtools view -H "$EBI_CRAM" 2>/dev/null | head -5 || echo "Also failed"
}

echo ""
echo "=== Alternative: Download from SRA ==="
echo "NA12878 WGS runs on SRA:"
echo "  ERR194147 (HiSeq 2500, 2x150, ~30x)"
echo "  SRR622461 (HiSeq 2000, 2x100, ~30x)"
echo ""
echo "Use prefetch + fasterq-dump from SRA toolkit for targeted download"
