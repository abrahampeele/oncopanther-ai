#!/bin/bash
# OncoPanther full pipeline launcher (FASTQs already downloaded)
source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export NXF_JAVA_HOME=/home/crak/miniconda3
export PATH=$JAVA_HOME/bin:/home/crak/miniconda3/bin:/home/crak/tools/Cyrius:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export TERM=dumb

PANTHER='/mnt/c/Users/drkat/OneDrive/Desktop/oncopanther-pgx/oncopanther-pgx/panther'
FASTA='/home/crak/references/GRCh38/GRCh38_full_analysis_set.fna'

echo '============================================================'
echo " OncoPanther-AI: Full Pipeline (FASTQs ready)"
echo " Sample: NA12878 / HG001 GIAB | Reference: GRCh38"
echo " Started: $(date)"
echo '============================================================'

cd "$PANTHER"

nextflow run main.nf \
  -c local.config \
  --fullmode \
  --input ./CSVs/3_samplesheetForAssembly_NA12878.csv \
  --reference "$FASTA" \
  --pgx \
  --pgxSources CPIC \
  --metaPatients ./CSVs/7_metaPatients_NA12878.csv \
  --metaYaml ./CSVs/7_metaPatients_NA12878.yml \
  --oncopantherLogo .oncopanther.png \
  --outdir ./outdir/NA12878 \
  -profile conda \
  -resume 2>&1

PIPELINE_EXIT=$?
echo ''
echo '============================================================'
echo " PIPELINE EXIT: $PIPELINE_EXIT"
echo " DONE: $(date)"
echo '============================================================'
exit $PIPELINE_EXIT
