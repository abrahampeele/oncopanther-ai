#!/bin/bash
source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base
export PATH=/home/crak/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

echo "=== Cyrius check ==="
which cyrius 2>/dev/null || echo "cyrius not in PATH"
python3 -c "import cyrius; print('cyrius module:', cyrius.__file__)" 2>/dev/null || echo "cyrius python module not found"
cyrius --version 2>/dev/null || echo "cyrius --version failed"

echo ""
echo "=== conda packages with cyrius ==="
conda list | grep -i cyrius

echo ""
echo "=== pip packages with cyrius ==="
pip show cyrius 2>/dev/null || echo "not in pip"

echo ""
echo "=== NA12878 BAM files available? ==="
ls -lh /home/crak/giab/NA12878/*.bam 2>/dev/null || echo "No BAM files found in /home/crak/giab/NA12878/"
