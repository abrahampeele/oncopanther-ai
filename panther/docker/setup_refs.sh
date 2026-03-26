#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# OncoPanther-AI — Reference Data Setup
# Downloads all reference data ONCE to a Docker volume.
# Subsequent runs use cached refs — no re-download needed.
#
# Called automatically on first run if refs are missing.
# ═══════════════════════════════════════════════════════════════════════════

REFS_DIR="${REFS_DIR:-/refs}"
LOG="${REFS_DIR}/setup.log"
STATUS_FILE="${REFS_DIR}/.setup_complete"

mkdir -p "$REFS_DIR"
mkdir -p "${REFS_DIR}/GRCh38"
mkdir -p "${REFS_DIR}/vep_cache"
mkdir -p "${REFS_DIR}/clinvar"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"
    # Also write to status file for web UI to read
    echo "$*" > "${REFS_DIR}/.setup_status"
}

log "=============================================="
log " OncoPanther-AI Reference Setup"
log " This runs ONCE — refs are cached forever"
log "=============================================="
log " Storage needed: ~40 GB"
log " Time estimate:  4-8 hours (internet speed)"
log "=============================================="

# ── STEP 1: GRCh38 Reference Genome ──────────────────────────────────────────
GRCh38_FA="${REFS_DIR}/GRCh38/GRCh38_full_analysis_set.fna"

if [ -f "$GRCh38_FA" ] && [ -f "${GRCh38_FA}.fai" ]; then
    log "✅ GRCh38 reference already present — skipping"
else
    log "📥 STEP 1/5: Downloading GRCh38 reference genome (~3.1 GB)..."
    log "   Source: GCP public bucket (free)"

    # Try GCP first (fastest for most regions)
    if command -v gsutil &>/dev/null; then
        gsutil -m cp \
            "gs://genomics-public-data/references/hg38/v0/Homo_sapiens_assembly38.fasta" \
            "$GRCh38_FA" 2>&1 | tee -a "$LOG"
        gsutil -m cp \
            "gs://genomics-public-data/references/hg38/v0/Homo_sapiens_assembly38.fasta.fai" \
            "${GRCh38_FA}.fai" 2>&1 | tee -a "$LOG"
    else
        # Fallback: NCBI FTP
        wget -q --show-progress \
            -O "$GRCh38_FA" \
            "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/000/001/405/GCA_000001405.15_GRCh38/seqs_for_alignment_pipelines.ucsc_ids/GCA_000001405.15_GRCh38_full_analysis_set.fna.gz" \
            2>&1 | tee -a "$LOG"
        gunzip -f "${GRCh38_FA}.gz" 2>&1 | tee -a "$LOG"
        samtools faidx "$GRCh38_FA" 2>&1 | tee -a "$LOG"
    fi
    log "✅ STEP 1/5: GRCh38 reference downloaded"
fi

# ── STEP 2: BWA-MEM2 Index ────────────────────────────────────────────────────
BWA_BWT="${REFS_DIR}/GRCh38/GRCh38_full_analysis_set.fna.bwt.2bit.64"

if [ -f "$BWA_BWT" ]; then
    log "✅ BWA-MEM2 index already present — skipping"
else
    log "📥 STEP 2/5: Building BWA-MEM2 index (~8 GB, ~1-2 hrs)..."
    log "   This is the longest step — only runs once"
    bwa-mem2 index "$GRCh38_FA" 2>&1 | tee -a "$LOG"
    log "✅ STEP 2/5: BWA-MEM2 index built"
fi

# ── STEP 3: VEP Cache ─────────────────────────────────────────────────────────
VEP_CACHE_DIR="${REFS_DIR}/vep_cache"
VEP_CHECK="${VEP_CACHE_DIR}/homo_sapiens/114_GRCh38"

if [ -d "$VEP_CHECK" ]; then
    log "✅ VEP cache already present — skipping"
else
    log "📥 STEP 3/5: Downloading VEP GRCh38 cache (~25 GB, 4-8 hrs)..."
    log "   Source: Ensembl FTP"
    VEP_TAR="${REFS_DIR}/vep_cache/homo_sapiens_vep_114_GRCh38.tar.gz"

    wget -c --progress=dot:mega \
        -O "$VEP_TAR" \
        "https://ftp.ensembl.org/pub/release-114/variation/indexed_vep_cache/homo_sapiens_vep_114_GRCh38.tar.gz" \
        2>&1 | tee -a "$LOG"

    log "   Extracting VEP cache..."
    tar -xzf "$VEP_TAR" -C "$VEP_CACHE_DIR" 2>&1 | tee -a "$LOG"
    rm -f "$VEP_TAR"
    log "✅ STEP 3/5: VEP cache ready"
fi

# ── STEP 4: ClinVar VCF ──────────────────────────────────────────────────────
CLINVAR_VCF="${REFS_DIR}/clinvar/clinvar.vcf.gz"

if [ -f "$CLINVAR_VCF" ] && [ -f "${CLINVAR_VCF}.tbi" ]; then
    log "✅ ClinVar VCF already present — skipping"
else
    log "📥 STEP 4/5: Downloading ClinVar VCF (~1 GB)..."
    # AWS Open Data (free)
    wget -q --show-progress \
        -O "$CLINVAR_VCF" \
        "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz" \
        2>&1 | tee -a "$LOG"
    wget -q --show-progress \
        -O "${CLINVAR_VCF}.tbi" \
        "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz.tbi" \
        2>&1 | tee -a "$LOG"
    log "✅ STEP 4/5: ClinVar ready"
fi

# ── STEP 5: GATK Dictionary ───────────────────────────────────────────────────
DICT="${REFS_DIR}/GRCh38/GRCh38_full_analysis_set.dict"

if [ -f "$DICT" ]; then
    log "✅ GATK dictionary already present — skipping"
else
    log "📥 STEP 5/5: Creating GATK sequence dictionary..."
    gatk CreateSequenceDictionary -R "$GRCh38_FA" -O "$DICT" 2>&1 | tee -a "$LOG"
    log "✅ STEP 5/5: GATK dictionary ready"
fi

# ── Mark setup complete ───────────────────────────────────────────────────────
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$STATUS_FILE"

log ""
log "=============================================="
log " ✅ ALL REFERENCES READY!"
log " GRCh38:   ${REFS_DIR}/GRCh38/"
log " VEP:      ${REFS_DIR}/vep_cache/homo_sapiens/"
log " ClinVar:  ${REFS_DIR}/clinvar/"
log " Space:    $(du -sh ${REFS_DIR} | cut -f1)"
log "=============================================="
log " OncoPanther is ready to run full pipelines!"
log "=============================================="
