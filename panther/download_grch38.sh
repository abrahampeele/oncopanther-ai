#!/bin/bash
# Download full GRCh38 analysis set reference genome to WSL2 filesystem
# NCBI analysis set: chr1-22, chrX, chrY, chrM + decoy sequences
# No ALT contigs (simplifies alignment) -- standard for GATK/WGS pipelines
set -euo pipefail

REFDIR=/home/crak/references/GRCh38
mkdir -p $REFDIR

URL="https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/000/001/405/GCA_000001405.15_GRCh38/seqs_for_alignment_pipelines.ucsc_ids/GCA_000001405.15_GRCh38_full_analysis_set.fna.gz"
FASTA_GZ="$REFDIR/GRCh38_full_analysis_set.fna.gz"
FASTA="$REFDIR/GRCh38_full_analysis_set.fna"

echo "=== Downloading GRCh38 full analysis set ==="
echo "Target: $FASTA_GZ"
echo "Size: ~900MB compressed, ~3GB uncompressed"
echo "URL: $URL"
echo ""

if [ -f "$FASTA" ]; then
    echo "Already exists: $FASTA — skipping download"
else
    curl -L --progress-bar -o "$FASTA_GZ" "$URL"
    echo ""
    echo "Decompressing..."
    gunzip "$FASTA_GZ"
fi

echo ""
echo "=== Verifying reference ==="
ls -lh $REFDIR/
echo ""
echo "Chromosome count:"
grep -c "^>" "$FASTA"
echo ""
echo "First 10 chromosomes:"
grep "^>" "$FASTA" | head -10
echo ""
echo "=== Done: $FASTA ==="
