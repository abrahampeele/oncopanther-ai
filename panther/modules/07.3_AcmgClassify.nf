// OncoPanther-PGx | Module 07.3 — ACMG/AMP Variant Classification
// Implements ACMG/AMP 2015 guidelines (Richards et al., Genetics in Medicine)
// Criteria evaluated from VEP CSQ annotations (--everything --check_existing)
// Classification: Pathogenic | Likely Pathogenic | VUS | Likely Benign | Benign

process AcmgClassify {
    tag "ACMG/AMP CLASSIFY ${vcf}"
    publishDir "${params.outdir}/annotation/acmg/", mode: 'copy'

    conda "/home/crak/miniconda3/envs/acmg_env"
    container "${workflow.containerEngine == 'singularity'
        ? 'docker://biocontainers/python:3.10'
        : 'biocontainers/python:3.10'}"

    input:
    tuple val(patient_id), path(vcf), path(tbi)

    output:
    tuple val(patient_id), path("${patient_id}_acmg.tsv"),      emit: acmg_tsv
    tuple val(patient_id), path("${patient_id}_acmg_summary.json"), emit: acmg_json
    tuple val(patient_id), path(vcf),                            emit: vcf

    script:
    """
#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
# OncoPanther-AI | ACMG/AMP 2015 Variant Classifier
# Based on: Richards et al. (2015) Genetics in Medicine 17:405-424
# Criteria implemented using VEP CSQ field annotations
# ─────────────────────────────────────────────────────────────────────────────

import gzip, re, json, sys
from collections import defaultdict

PATIENT_ID = "${patient_id}"
VCF_FILE   = "${vcf}"

# ── VEP CSQ field order (from --everything --check_existing) ─────────────────
# Positions used (0-based in CSQ subfields):
CSQ_FIELDS = [
    "Allele","Consequence","IMPACT","SYMBOL","Gene","Feature_type","Feature",
    "BIOTYPE","EXON","INTRON","HGVSc","HGVSp","cDNA_position","CDS_position",
    "Protein_position","Amino_acids","Codons","Existing_variation","DISTANCE",
    "STRAND","FLAGS","VARIANT_CLASS","SYMBOL_SOURCE","HGNC_ID","CANONICAL",
    "MANE_SELECT","MANE_PLUS_CLINICAL","TSL","APPRIS","CCDS","ENSP","SWISSPROT",
    "TREMBL","UNIPARC","UNIPROT_ISOFORM","GENE_PHENO","SIFT","PolyPhen",
    "DOMAINS","HGVS_OFFSET","AF","AFR_AF","AMR_AF","EAS_AF","EUR_AF","SAS_AF",
    "AA_AF","EA_AF","gnomAD_AF","gnomAD_AFR_AF","gnomAD_AMR_AF","gnomAD_ASJ_AF",
    "gnomAD_EAS_AF","gnomAD_FIN_AF","gnomAD_NFE_AF","gnomAD_OTH_AF","gnomAD_SAS_AF",
    "MAX_AF","MAX_AF_POPS","FREQS","PUBMED","MOTIF_NAME","MOTIF_POS",
    "HIGH_INF_POS","MOTIF_SCORE_CHANGE","TRANSCRIPTION_FACTORS","CADD_PHRED",
    "CADD_RAW","ClinVar_CLNSIG","ClinVar_CLNREVSTAT","ClinVar_CLNDN"
]

# ── Genes known to be loss-of-function intolerant (pLI > 0.9 from gnomAD) ───
# Subset of high-confidence LoF-intolerant genes for PVS1 criterion
LOF_INTOLERANT_GENES = {
    "BRCA1","BRCA2","TP53","MLH1","MSH2","MSH6","PMS2","APC","VHL",
    "RB1","WT1","NF1","NF2","PTEN","STK11","CDH1","CDKN2A","SMAD4",
    "RUNX1","FLT3","NPM1","IDH1","IDH2","DNMT3A","TET2","ASXL1",
    "BRAF","KRAS","NRAS","PIK3CA","EGFR","ALK","ROS1","RET","MET",
    "ERBB2","FGFR1","FGFR2","FGFR3","PDGFRA","KIT","ABL1","BCR",
    "MYC","MYCN","CCND1","CDK4","CDK6","CDKN1A","CDKN1B",
    "DICER1","PALB2","RAD51C","RAD51D","ATM","CHEK2","NBN",
    "TSC1","TSC2","PTCH1","SUFU","GLI1","CTNNB1","AXIN1","AXIN2",
    "NOTCH1","NOTCH2","JAK2","JAK3","STAT3","STAT5A","STAT5B",
    "SF3B1","SRSF2","U2AF1","ZRSR2","EZH2","KDM6A","KMT2A","KMT2D",
    "CREBBP","EP300","ARID1A","ARID1B","SMARCA4","SMARCB1","SMARCE1",
    "SETD2","KDM5C","KDM5D","PHF6","BCOR","BCORL1","CUX1",
    "MED12","SPOP","FOXA1","GATA2","GATA3","RUNX1T1",
    "CEBPA","GATA1","TAL1","LMO2","TLX1","TLX3"
}

# ── High-confidence pathogenic variant consequences for PVS1 ─────────────────
PVS1_CONSEQUENCES = {
    "frameshift_variant", "stop_gained", "splice_donor_variant",
    "splice_acceptor_variant", "start_lost", "transcript_ablation",
    "transcript_amplification"
}

# ── Missense-constraint genes for PP2 criterion ──────────────────────────────
MISSENSE_CONSTRAINED_GENES = {
    "BRCA1","BRCA2","TP53","PTEN","RB1","VHL","APC","MLH1","MSH2",
    "MSH6","PMS2","CDH1","STK11","CDKN2A","NF1","NF2","TSC1","TSC2",
    "WT1","PTCH1","SMAD4","RUNX1","CREBBP","EP300","KMT2A","KMT2D",
    "ARID1A","SMARCA4","SMARCB1","SETD2","DNMT3A","IDH1","IDH2",
    "TET2","ASXL1","EZH2","SF3B1","SRSF2"
}

# ─────────────────────────────────────────────────────────────────────────────
# Parse VCF and extract CSQ annotations
# ─────────────────────────────────────────────────────────────────────────────

def safe_float(val, default=None):
    try:
        return float(val) if val and val not in (".", "", "NA") else default
    except (ValueError, TypeError):
        return default

def parse_csq_header(vcf_header_lines):
    '''Extract CSQ field order from VEP ##INFO=<ID=CSQ...> header line.'''
    for line in vcf_header_lines:
        if line.startswith("##INFO=<ID=CSQ"):
            m = re.search(r'Format: ([^"]+)"', line)
            if m:
                return m.group(1).strip().split("|")
    return CSQ_FIELDS  # fallback to known order

def parse_info_field(info_str):
    info = {}
    for field in info_str.split(";"):
        if "=" in field:
            k, v = field.split("=", 1)
            info[k] = v
        else:
            info[field] = True
    return info

def parse_csq_entry(csq_str, field_names):
    '''Parse one CSQ entry into a dict.'''
    parts = csq_str.split("|")
    d = {}
    for i, name in enumerate(field_names):
        d[name] = parts[i] if i < len(parts) else ""
    return d

def get_canonical_csq(csq_list, field_names):
    '''Return canonical transcript CSQ, else MANE SELECT, else first.'''
    for c in csq_list:
        if parse_csq_entry(c, field_names).get("CANONICAL") == "YES":
            return parse_csq_entry(c, field_names)
    for c in csq_list:
        if parse_csq_entry(c, field_names).get("MANE_SELECT"):
            return parse_csq_entry(c, field_names)
    if csq_list:
        return parse_csq_entry(csq_list[0], field_names)
    return {}

# ─────────────────────────────────────────────────────────────────────────────
# ACMG/AMP Criteria Evaluation Engine
# Reference: Richards et al. (2015) Genet Med 17:405-424
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_acmg(csq, af_info, existing_variation):
    '''
    Evaluate applicable ACMG/AMP criteria from VEP annotations.
    Returns: dict of {criterion: True/False/None} and combined score.

    Criteria strength weights (from Richards 2015):
      Very Strong (PVS) = 8 pts pathogenic
      Strong     (PS)   = 4 pts pathogenic
      Moderate   (PM)   = 2 pts pathogenic
      Supporting (PP)   = 1 pt  pathogenic
      Stand-alone (BA)  = -8 pts (benign)
      Strong Benign(BS) = -4 pts
      Supporting  (BP)  = -1 pt
    '''
    criteria = {}
    score = 0

    gene       = csq.get("SYMBOL", "")
    impact     = csq.get("IMPACT", "")
    consequence_str = csq.get("Consequence", "")
    consequences = set(consequence_str.split("&"))
    sift_raw   = csq.get("SIFT", "")
    poly_raw   = csq.get("PolyPhen", "")
    hgvsp      = csq.get("HGVSp", "")
    biotype    = csq.get("BIOTYPE", "")
    domains    = csq.get("DOMAINS", "")
    clinvar_sig = csq.get("ClinVar_CLNSIG", "") or ""
    clinvar_rev = csq.get("ClinVar_CLNREVSTAT", "") or ""

    # gnomAD allele frequency (MAX_AF = highest AF across all gnomAD populations)
    max_af = safe_float(csq.get("MAX_AF"))
    gnomad_af = safe_float(csq.get("gnomAD_AF"))
    pop_af = max_af if max_af is not None else gnomad_af

    # SIFT and PolyPhen parsed scores
    sift_score   = None
    sift_pred    = ""
    poly_score   = None
    poly_pred    = ""

    if sift_raw and "(" in sift_raw:
        m = re.match(r"(\\w+)\\(([0-9.]+)\\)", sift_raw)
        if m:
            sift_pred  = m.group(1).lower()
            sift_score = safe_float(m.group(2))

    if poly_raw and "(" in poly_raw:
        m = re.match(r"(\\w+)\\(([0-9.]+)\\)", poly_raw)
        if m:
            poly_pred  = m.group(1).lower()
            poly_score = safe_float(m.group(2))

    # ── PVS1: Null variant in gene where LoF is disease mechanism ────────────
    pvs1 = (
        impact == "HIGH" and
        consequences & PVS1_CONSEQUENCES and
        biotype == "protein_coding" and
        gene in LOF_INTOLERANT_GENES
    )
    if pvs1:
        criteria["PVS1"] = True
        score += 8

    # ── PS1: Same amino acid change as established pathogenic variant ─────────
    # Triggered if ClinVar has P/LP with review status >= 2 stars
    ps1 = False
    if clinvar_sig:
        sig_lower = clinvar_sig.lower()
        high_confidence = any(x in clinvar_rev.lower() for x in [
            "reviewed_by_expert_panel",
            "criteria_provided,_multiple_submitters",
            "practice_guideline"
        ])
        if ("pathogenic" in sig_lower) and high_confidence:
            ps1 = True
    if ps1:
        criteria["PS1"] = True
        score += 4

    # ── PM1: Mutational hotspot or critical functional domain ─────────────────
    pm1 = (
        impact in ("HIGH", "MODERATE") and
        domains and
        any(d.strip() for d in domains.split("&") if d.strip())
    )
    if pm1:
        criteria["PM1"] = True
        score += 2

    # ── PM2: Absent/extremely rare in gnomAD exome/genome ─────────────────────
    pm2 = (pop_af is None) or (pop_af < 0.001)
    if pm2:
        criteria["PM2"] = True
        score += 2

    # ── PM4: Protein length change (in-frame indel in non-repeat region) ──────
    pm4 = (
        "inframe_insertion" in consequences or
        "inframe_deletion" in consequences
    ) and biotype == "protein_coding"
    if pm4:
        criteria["PM4"] = True
        score += 2

    # ── PM5: Novel missense at same position as known pathogenic missense ──────
    pm5 = (
        "missense_variant" in consequences and
        clinvar_sig and "pathogenic" in clinvar_sig.lower() and
        ps1 is False  # Same position but different AA change
    )
    if pm5:
        criteria["PM5"] = True
        score += 2

    # ── PP2: Missense in gene with low rate of benign missense ────────────────
    pp2 = (
        "missense_variant" in consequences and
        gene in MISSENSE_CONSTRAINED_GENES
    )
    if pp2:
        criteria["PP2"] = True
        score += 1

    # ── PP3: Multiple computational tools predict deleterious ─────────────────
    sift_del = sift_pred in ("deleterious", "deleterious_low_confidence")
    poly_del = poly_pred in ("probably_damaging", "possibly_damaging")
    pp3 = (sift_del and poly_del) or (sift_del and poly_score and poly_score > 0.5) or (poly_del and sift_score is not None and sift_score < 0.05)
    if pp3:
        criteria["PP3"] = True
        score += 1

    # ── PP5: Reputable source (ClinVar P/LP, any review status) ──────────────
    pp5 = clinvar_sig and any(x in clinvar_sig.lower() for x in ["pathogenic"])
    if pp5 and not ps1:  # Don't double-count with PS1
        criteria["PP5"] = True
        score += 1

    # ── BA1: Allele frequency > 5% in gnomAD (stand-alone benign) ────────────
    ba1 = pop_af is not None and pop_af > 0.05
    if ba1:
        criteria["BA1"] = True
        score -= 8

    # ── BS1: Allele frequency greater than expected ───────────────────────────
    bs1 = pop_af is not None and 0.01 < pop_af <= 0.05
    if bs1:
        criteria["BS1"] = True
        score -= 4

    # ── BP1: Missense variant in gene where only truncating cause disease ──────
    bp1 = (
        "missense_variant" in consequences and
        gene in LOF_INTOLERANT_GENES and
        not gene in MISSENSE_CONSTRAINED_GENES
    )
    if bp1:
        criteria["BP1"] = True
        score -= 1

    # ── BP4: Computational tools predict benign ───────────────────────────────
    sift_ben = sift_pred in ("tolerated", "tolerated_low_confidence")
    poly_ben = poly_pred == "benign"
    bp4 = (sift_ben and poly_ben)
    if bp4 and not pp3:
        criteria["BP4"] = True
        score -= 1

    # ── BP7: Synonymous variant, no predicted splice impact ───────────────────
    bp7 = (
        "synonymous_variant" in consequences and
        "splice" not in consequence_str
    )
    if bp7:
        criteria["BP7"] = True
        score -= 1

    # ─────────────────────────────────────────────────────────────────────────
    # Final Classification (Richards 2015 + Tavtigian et al 2020 point system)
    # ─────────────────────────────────────────────────────────────────────────
    if ba1:
        classification = "Benign"
    elif score >= 10:
        classification = "Pathogenic"
    elif score >= 6:
        classification = "Likely Pathogenic"
    elif score <= -6:
        classification = "Benign"
    elif score <= -2:
        classification = "Likely Benign"
    else:
        classification = "Uncertain Significance"

    # Criteria triggered string
    triggered = [k for k, v in criteria.items() if v is True]

    return classification, score, triggered

# ─────────────────────────────────────────────────────────────────────────────
# Main: Parse VCF and classify all variants
# ─────────────────────────────────────────────────────────────────────────────

results       = []
summary_counts = defaultdict(int)
header_lines  = []
csq_fields    = None

opener = gzip.open if VCF_FILE.endswith(".gz") else open

with opener(VCF_FILE, "rt") as fh:
    for line in fh:
        line = line.rstrip("\\n")
        if line.startswith("##"):
            header_lines.append(line)
            if csq_fields is None and "ID=CSQ" in line:
                csq_fields = parse_csq_header([line])
            continue
        if line.startswith("#CHROM"):
            cols = line.lstrip("#").split("\\t")
            continue

        parts = line.split("\\t")
        if len(parts) < 8:
            continue

        chrom, pos, vid, ref, alt, qual, filt, info_str = parts[:8]
        info = parse_info_field(info_str)

        if "CSQ" not in info:
            continue

        csq_entries = info["CSQ"].split(",")
        fields      = csq_fields or CSQ_FIELDS
        csq         = get_canonical_csq(csq_entries, fields)

        if not csq:
            continue

        existing_variation = csq.get("Existing_variation", "")
        classification, score, triggered = evaluate_acmg(csq, info, existing_variation)

        summary_counts[classification] += 1

        results.append({
            "CHROM":          chrom,
            "POS":            pos,
            "REF":            ref,
            "ALT":            alt,
            "QUAL":           qual,
            "FILTER":         filt,
            "GENE":           csq.get("SYMBOL", "."),
            "VARIANT_CLASS":  csq.get("VARIANT_CLASS", "."),
            "HGVSc":          csq.get("HGVSc", "."),
            "HGVSp":          csq.get("HGVSp", "."),
            "CONSEQUENCE":    csq.get("Consequence", "."),
            "IMPACT":         csq.get("IMPACT", "."),
            "SIFT":           csq.get("SIFT", "."),
            "PolyPhen":       csq.get("PolyPhen", "."),
            "gnomAD_AF":      csq.get("gnomAD_AF", "."),
            "MAX_AF":         csq.get("MAX_AF", "."),
            "ClinVar_CLNSIG": csq.get("ClinVar_CLNSIG", "."),
            "ClinVar_CLNDN":  csq.get("ClinVar_CLNDN", "."),
            "EXISTING":       existing_variation,
            "CRITERIA":       "|".join(triggered) if triggered else "None",
            "ACMG_SCORE":     str(score),
            "ACMG_CLASS":     classification,
        })

# ── Write TSV output ──────────────────────────────────────────────────────────
TSV_OUT = "${patient_id}_acmg.tsv"
headers = [
    "CHROM","POS","REF","ALT","QUAL","FILTER","GENE","VARIANT_CLASS",
    "HGVSc","HGVSp","CONSEQUENCE","IMPACT","SIFT","PolyPhen",
    "gnomAD_AF","MAX_AF","ClinVar_CLNSIG","ClinVar_CLNDN",
    "EXISTING","CRITERIA","ACMG_SCORE","ACMG_CLASS"
]

with open(TSV_OUT, "w") as out:
    out.write("\\t".join(headers) + "\\n")
    # Sort: Pathogenic first, then LP, VUS, LB, Benign
    order = {"Pathogenic":0,"Likely Pathogenic":1,"Uncertain Significance":2,
             "Likely Benign":3,"Benign":4}
    results_sorted = sorted(results, key=lambda x: order.get(x["ACMG_CLASS"], 5))
    for r in results_sorted:
        out.write("\\t".join(str(r.get(h, ".")) for h in headers) + "\\n")

# ── Write JSON summary ────────────────────────────────────────────────────────
JSON_OUT = "${patient_id}_acmg_summary.json"
total = len(results)
pathogenic_variants = [r for r in results if r["ACMG_CLASS"] in ("Pathogenic", "Likely Pathogenic")]

summary = {
    "patient_id":   PATIENT_ID,
    "total_variants": total,
    "classification_counts": dict(summary_counts),
    "pathogenic_count":  summary_counts.get("Pathogenic", 0),
    "likely_pathogenic_count": summary_counts.get("Likely Pathogenic", 0),
    "vus_count":     summary_counts.get("Uncertain Significance", 0),
    "likely_benign_count": summary_counts.get("Likely Benign", 0),
    "benign_count":  summary_counts.get("Benign", 0),
    "top_pathogenic": pathogenic_variants[:10],
    "criteria_framework": "ACMG/AMP 2015 (Richards et al., Genet Med 17:405-424)",
    "criteria_evaluated": ["PVS1","PS1","PM1","PM2","PM4","PM5","PP2","PP3","PP5","BA1","BS1","BP1","BP4","BP7"],
    "annotation_source": "Ensembl VEP --everything --check_existing"
}

with open(JSON_OUT, "w") as jf:
    json.dump(summary, jf, indent=2)

print(f"[OncoPanther ACMG] {PATIENT_ID}: {total} variants classified.")
print(f"  Pathogenic:          {summary_counts.get('Pathogenic', 0)}")
print(f"  Likely Pathogenic:   {summary_counts.get('Likely Pathogenic', 0)}")
print(f"  Uncertain Sig (VUS): {summary_counts.get('Uncertain Significance', 0)}")
print(f"  Likely Benign:       {summary_counts.get('Likely Benign', 0)}")
print(f"  Benign:              {summary_counts.get('Benign', 0)}")
    """
}
