#!/bin/bash
source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base
export PATH=/home/crak/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export TERM=dumb

echo "=== Checking EBI SRA ERR194147 (NA12878 WGS) ==="
# List files in EBI SRA directory
curl -s "http://ftp.sra.ebi.ac.uk/vol1/run/ERR194/ERR194147/" 2>/dev/null | grep -oP 'href="[^"]*"' | head -20

echo ""
echo "=== Checking EBI FASTQ FTP ==="
# EBI also keeps FASTQs at a different path
curl -s "ftp://ftp.sra.ebi.ac.uk/vol1/fastq/ERR194/ERR194147/" 2>/dev/null | head -10 || echo "FTP access blocked"

echo ""
echo "=== Checking if BAM is available for streaming ==="
curl -s --head "http://ftp.sra.ebi.ac.uk/vol1/run/ERR194/ERR194147/NA12878.bam" 2>/dev/null | grep -E "HTTP|Content-Length|Last-Modified" | head -5 || echo "BAM not found"

curl -s --head "http://ftp.sra.ebi.ac.uk/vol1/run/ERR194/ERR194147/NA12878.bam.bai" 2>/dev/null | grep -E "HTTP|Content-Length" | head -3 || echo "BAI not found"

echo ""
echo "=== prefetch check ==="
prefetch --version 2>&1 | head -2
echo "prefetch path: $(which prefetch)"

echo ""
echo "=== BWA index progress ==="
tail -3 /home/crak/bwa_index.log
ls -lh /home/crak/references/GRCh38/*.pac 2>/dev/null || echo ".pac still empty/writing"
