#!/bin/bash
# OncoPanther: PGx stepmode on real NA12878 GIAB VCF
LOG=/home/crak/pgx_giab_run.log
exec > >(tee -a $LOG) 2>&1

source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base

export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export NXF_JAVA_HOME=/home/crak/miniconda3
PANTHER='/mnt/c/Users/drkat/OneDrive/Desktop/oncopanther-pgx/oncopanther-pgx/panther'
export PATH=$JAVA_HOME/bin:/home/crak/miniconda3/bin:/home/crak/tools/Cyrius:$PANTHER:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PYTHONPATH=$PANTHER:${PYTHONPATH:-}
export TERM=dumb

echo "============================================================"
echo " OncoPanther-AI: PGx Analysis — Real GIAB NA12878 VCF"
echo " Data: HG001_GRCh38_GIAB_NA12878_pharmcat_ready.vcf.gz"
echo " Started: $(date)"
echo "============================================================"
echo "Java:     $(java -version 2>&1 | head -1)"
echo "Nextflow: $(nextflow -version 2>&1 | grep version | head -1)"
echo ""

VCF=/home/crak/giab/NA12878/HG001_GRCh38_GIAB_NA12878_pharmcat_ready.vcf.gz
if [ ! -f "$VCF" ]; then
  echo "ERROR: Real GIAB VCF not found: $VCF"; exit 1
fi
echo "✓ Real GIAB VCF: $(ls -lh $VCF | awk '{print $5, $9}')"
echo ""

cd $PANTHER

nextflow run main.nf \
  -c local.config \
  --stepmode \
  --exec pgx \
  --pgxVcf ./CSVs/8_samplesheetPgx_NA12878.csv \
  --pgxSources CPIC \
  --metaPatients ./CSVs/7_metaPatients_NA12878.csv \
  --metaYaml ./CSVs/7_metaPatients_NA12878.yml \
  --oncopantherLogo .oncopanther.png \
  --outdir ./outdir/NA12878 \
  -profile conda \
  -resume 2>&1

echo ""
echo "============================================================"
echo " PGx RUN COMPLETE: $(date)"
echo " Results: $PANTHER/outdir/NA12878/"
echo "============================================================"
