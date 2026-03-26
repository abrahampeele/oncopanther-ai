#!/bin/bash
source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base
export PATH=/home/crak/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export TERM=dumb

echo "=== Checking NA12878 data sources for PGx pipeline ==="
echo ""

# Option 1: GIAB GRCh38 HiSeq BAM index (HTTP streaming)
GIAB_GRCh38_BAM="https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/data/NA12878/Genome_in_a_Bottle_v0.2/2014-10-14_Justin_BioProject_PRJNA200694_backup_Illumina_2x150bpTruSeq_HiSeqX/Combined/HG001.hs37d5.300x.bam"

echo "Option 1: GIAB HiSeq streaming BAM (GRCh37, need to realign)"
echo "Testing HTTP access..."
curl -s --head "$GIAB_GRCh38_BAM" 2>/dev/null | head -3 || echo "GIAB BAM not accessible via curl"

echo ""
# Option 2: EBI 1000G NA12878 CRAM (GRCh38)
EBI_CRAM="http://ftp.1000genomes.ebi.ac.uk/vol1/ftp/data_collections/1000_genomes_project/data/CEU/NA12878/alignment/NA12878.alt_bwamem_GRCh38DH.20150706.CEU.low_coverage.cram"
echo "Option 2: EBI 1000G CRAM (GRCh38, low-coverage ~4x)"
curl -s --head "$EBI_CRAM" 2>/dev/null | grep -E "HTTP|Content-Length" | head -3 || echo "Not accessible"

echo ""
# Option 3: Check EBI FTP for NA12878 GRCh38 high-coverage CRAM
EBI_HIGH="http://ftp.sra.ebi.ac.uk/vol1/run/ERR194/ERR194147/NA12878.mapped.ILLUMINA.bwa.CEU.low_coverage.20121211.bam.bai"
echo "Option 3: EBI SRA ERR194147 (NA12878 WGS)"
curl -s --head "http://ftp.sra.ebi.ac.uk/vol1/run/ERR194/ERR194147/" 2>/dev/null | head -3

echo ""
# Check SRA-tools available
echo "=== SRA tools check ==="
which prefetch 2>/dev/null && prefetch --version 2>/dev/null | head -1 || echo "prefetch not installed"
which fasterq-dump 2>/dev/null && fasterq-dump --version 2>/dev/null | head -1 || echo "fasterq-dump not installed"

echo ""
# Check if we can use the existing GIAB BAM already on disk to extract FASTQs
echo "=== Existing BAM files from toy data ==="
ls -lh /mnt/c/Users/drkat/OneDrive/Desktop/oncopanther-pgx/oncopanther-pgx/panther/outdir/Mapping/*.bam 2>/dev/null

echo ""
echo "=== BWA index progress ==="
tail -4 /home/crak/bwa_index.log 2>/dev/null
ls -lh /home/crak/references/GRCh38/*.pac /home/crak/references/GRCh38/*.bwt 2>/dev/null || echo "Index files not ready yet"
