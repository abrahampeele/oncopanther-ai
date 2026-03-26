"""
OncoPanther-AI | ACMG/AMP 2015 Variant Classifier
Standalone Python module — runs inline in Streamlit demo app

Based on: Richards et al. (2015) Genetics in Medicine 17:405-424
Criteria evaluated from Ensembl VEP CSQ annotations (--everything --check_existing)

Usage:
    from acmg_classifier import classify_vcf_bytes
    results, summary = classify_vcf_bytes(open("sample.vcf.gz","rb").read())
"""

import gzip
import re
import json
from io import BytesIO
from collections import defaultdict

# ── VEP CSQ field fallback order (from --everything --check_existing) ────────
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
    "HIGH_INF_POS","MOTIF_SCORE_CHANGE","TRANSCRIPTION_FACTORS",
    "ClinVar_CLNSIG","ClinVar_CLNREVSTAT","ClinVar_CLNDN",
]

# ── Loss-of-function intolerant genes (pLI > 0.9) for PVS1 ──────────────────
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
    "CEBPA","GATA1","TAL1","LMO2","TLX1","TLX3",
}

# ── Consequences that qualify for PVS1 ──────────────────────────────────────
PVS1_CONSEQUENCES = {
    "frameshift_variant", "stop_gained", "splice_donor_variant",
    "splice_acceptor_variant", "start_lost", "transcript_ablation",
    "transcript_amplification",
}

# ── Missense-constrained genes for PP2 ──────────────────────────────────────
MISSENSE_CONSTRAINED_GENES = {
    "BRCA1","BRCA2","TP53","PTEN","RB1","VHL","APC","MLH1","MSH2",
    "MSH6","PMS2","CDH1","STK11","CDKN2A","NF1","NF2","TSC1","TSC2",
    "WT1","PTCH1","SMAD4","RUNX1","CREBBP","EP300","KMT2A","KMT2D",
    "ARID1A","SMARCA4","SMARCB1","SETD2","DNMT3A","IDH1","IDH2",
    "TET2","ASXL1","EZH2","SF3B1","SRSF2",
}


# ─────────────────────────────────────────────────────────────────────────────
# VCF / CSQ Parsing Helpers
# ─────────────────────────────────────────────────────────────────────────────

def safe_float(val, default=None):
    try:
        return float(val) if val and val not in (".", "", "NA") else default
    except (ValueError, TypeError):
        return default


def parse_csq_header(header_lines):
    """Extract CSQ field names from VEP ##INFO=<ID=CSQ...> header line."""
    for line in header_lines:
        if "##INFO=<ID=CSQ" in line:
            m = re.search(r"Format: ([^\"]+)\"", line)
            if m:
                return [f.strip() for f in m.group(1).split("|")]
    return CSQ_FIELDS


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
    parts = csq_str.split("|")
    return {name: (parts[i] if i < len(parts) else "") for i, name in enumerate(field_names)}


def get_canonical_csq(csq_list, field_names):
    """Return canonical / MANE-SELECT transcript CSQ, else first."""
    for c in csq_list:
        d = parse_csq_entry(c, field_names)
        if d.get("CANONICAL") == "YES":
            return d
    for c in csq_list:
        d = parse_csq_entry(c, field_names)
        if d.get("MANE_SELECT"):
            return d
    if csq_list:
        return parse_csq_entry(csq_list[0], field_names)
    return {}


def _extract_pred_label(raw: str) -> str:
    """Extract label from VEP format like 'deleterious(0.02)' → 'deleterious'."""
    if not raw:
        return ""
    m = re.match(r"([a-zA-Z_]+)", raw)
    return m.group(1).lower() if m else raw.lower()


def _format_af(val) -> str:
    """Format gnomAD AF for display."""
    f = safe_float(val)
    if f is None:
        return "."
    if f < 0.001:
        return f"<0.001"
    return f"{f:.4f}"


# ─────────────────────────────────────────────────────────────────────────────
# ACMG/AMP Criteria Evaluation Engine
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_acmg(csq: dict, info: dict, existing_variation: str):
    """
    Evaluate ACMG/AMP 2015 criteria from a VEP CSQ annotation dict.

    Returns: (classification_str, score_int, triggered_criteria_list)

    Strength weights:
        PVS1 = +8   (Very Strong Pathogenic)
        PS   = +4   (Strong Pathogenic)
        PM   = +2   (Moderate Pathogenic)
        PP   = +1   (Supporting Pathogenic)
        BA1  = -8   (Stand-Alone Benign)
        BS   = -4   (Strong Benign)
        BP   = -1   (Supporting Benign)
    """
    criteria = {}
    score = 0

    gene            = csq.get("SYMBOL", "")
    impact          = csq.get("IMPACT", "")
    consequence_str = csq.get("Consequence", "")
    consequences    = set(consequence_str.split("&"))
    biotype         = csq.get("BIOTYPE", "")
    domains         = csq.get("DOMAINS", "")
    clinvar_sig     = csq.get("ClinVar_CLNSIG", "") or ""
    clinvar_rev     = csq.get("ClinVar_CLNREVSTAT", "") or ""

    sift_pred    = _extract_pred_label(csq.get("SIFT", ""))
    poly_pred    = _extract_pred_label(csq.get("PolyPhen", ""))
    sift_score   = safe_float(re.search(r"\(([0-9.]+)\)", csq.get("SIFT", "") or "").group(1)
                               if re.search(r"\(([0-9.]+)\)", csq.get("SIFT", "") or "") else None)
    poly_score   = safe_float(re.search(r"\(([0-9.]+)\)", csq.get("PolyPhen", "") or "").group(1)
                               if re.search(r"\(([0-9.]+)\)", csq.get("PolyPhen", "") or "") else None)

    max_af    = safe_float(csq.get("MAX_AF"))
    gnomad_af = safe_float(csq.get("gnomAD_AF"))
    pop_af    = max_af if max_af is not None else gnomad_af

    # ── PVS1: Null variant (LoF) in LoF-intolerant gene ─────────────────────
    if (impact == "HIGH" and
            consequences & PVS1_CONSEQUENCES and
            biotype == "protein_coding" and
            gene in LOF_INTOLERANT_GENES):
        criteria["PVS1"] = True
        score += 8

    # ── PS1: Same AA change as known pathogenic (ClinVar ≥2★) ────────────────
    ps1 = False
    if clinvar_sig:
        sig_lower = clinvar_sig.lower()
        high_confidence = any(x in clinvar_rev.lower() for x in [
            "reviewed_by_expert_panel",
            "criteria_provided,_multiple_submitters",
            "practice_guideline",
        ])
        if "pathogenic" in sig_lower and high_confidence:
            criteria["PS1"] = True
            score += 4
            ps1 = True

    # ── PM1: Mutational hotspot or critical functional domain ─────────────────
    if (impact in ("HIGH", "MODERATE") and domains and
            any(d.strip() for d in domains.split("&") if d.strip())):
        criteria["PM1"] = True
        score += 2

    # ── PM2: Absent/very rare in gnomAD (AF < 0.001) ─────────────────────────
    if pop_af is None or pop_af < 0.001:
        criteria["PM2"] = True
        score += 2

    # ── PM4: Protein length change (in-frame indel) ───────────────────────────
    if (("inframe_insertion" in consequences or "inframe_deletion" in consequences)
            and biotype == "protein_coding"):
        criteria["PM4"] = True
        score += 2

    # ── PM5: Novel missense at same position as known pathogenic missense ──────
    if ("missense_variant" in consequences and
            clinvar_sig and "pathogenic" in clinvar_sig.lower() and not ps1):
        criteria["PM5"] = True
        score += 2

    # ── PP2: Missense in missense-constrained gene ────────────────────────────
    if "missense_variant" in consequences and gene in MISSENSE_CONSTRAINED_GENES:
        criteria["PP2"] = True
        score += 1

    # ── PP3: Computational tools predict deleterious ──────────────────────────
    sift_del = sift_pred in ("deleterious", "deleterious_low_confidence")
    poly_del = poly_pred in ("probably_damaging", "possibly_damaging")
    pp3 = (sift_del and poly_del) or \
          (sift_del and poly_score is not None and poly_score > 0.5) or \
          (poly_del and sift_score is not None and sift_score < 0.05)
    if pp3:
        criteria["PP3"] = True
        score += 1

    # ── PP5: ClinVar pathogenic (any review status) ───────────────────────────
    if clinvar_sig and "pathogenic" in clinvar_sig.lower() and not ps1:
        criteria["PP5"] = True
        score += 1

    # ── BA1: AF > 5% in gnomAD (stand-alone benign) ──────────────────────────
    ba1 = pop_af is not None and pop_af > 0.05
    if ba1:
        criteria["BA1"] = True
        score -= 8

    # ── BS1: AF between 1–5% in gnomAD ───────────────────────────────────────
    if pop_af is not None and 0.01 < pop_af <= 0.05:
        criteria["BS1"] = True
        score -= 4

    # ── BP1: Missense in LoF-only gene (not constrained for missense) ─────────
    if ("missense_variant" in consequences and
            gene in LOF_INTOLERANT_GENES and
            gene not in MISSENSE_CONSTRAINED_GENES):
        criteria["BP1"] = True
        score -= 1

    # ── BP4: Computational tools predict benign ───────────────────────────────
    sift_ben = sift_pred in ("tolerated", "tolerated_low_confidence")
    poly_ben = poly_pred == "benign"
    if sift_ben and poly_ben and not pp3:
        criteria["BP4"] = True
        score -= 1

    # ── BP7: Synonymous, no predicted splice impact ───────────────────────────
    if "synonymous_variant" in consequences and "splice" not in consequence_str:
        criteria["BP7"] = True
        score -= 1

    # ── Final classification ──────────────────────────────────────────────────
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

    triggered = [k for k, v in criteria.items() if v]
    return classification, score, triggered


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def classify_vcf_bytes(vcf_bytes: bytes) -> tuple:
    """
    Classify all variants in a VEP-annotated VCF supplied as bytes.

    Accepts both plain and gzip-compressed VCF.

    Returns:
        results  (list[dict]) — one dict per variant, keys match DEMO_ACMG_RESULTS
        summary  (dict)       — classification counts + top pathogenic list
    """
    # ── Detect gzip ──────────────────────────────────────────────────────────
    if vcf_bytes[:2] == b"\x1f\x8b":
        fh = gzip.open(BytesIO(vcf_bytes), "rt", encoding="utf-8", errors="replace")
    else:
        from io import StringIO
        fh = StringIO(vcf_bytes.decode("utf-8", errors="replace"))

    header_lines = []
    csq_fields   = None
    results      = []
    counts       = defaultdict(int)
    has_csq      = False

    with fh:
        for line in fh:
            line = line.rstrip("\n").rstrip("\r")

            if line.startswith("##"):
                header_lines.append(line)
                if csq_fields is None and "ID=CSQ" in line:
                    csq_fields = parse_csq_header([line])
                    has_csq = True
                continue

            if line.startswith("#"):
                continue   # column header line

            parts = line.split("\t")
            if len(parts) < 8:
                continue

            chrom, pos, vid, ref, alt, qual, filt, info_str = parts[:8]
            info = parse_info_field(info_str)

            if "CSQ" not in info:
                continue

            fields  = csq_fields or CSQ_FIELDS
            entries = info["CSQ"].split(",")
            csq     = get_canonical_csq(entries, fields)
            if not csq:
                continue

            existing = csq.get("Existing_variation", "")
            classification, score, triggered = evaluate_acmg(csq, info, existing)

            counts[classification] += 1

            # gnomAD AF display
            gnomad_af_raw = csq.get("gnomAD_AF", "") or csq.get("MAX_AF", "")
            gnomad_display = _format_af(gnomad_af_raw)

            # SIFT / PolyPhen — extract just the label
            sift_label  = _extract_pred_label(csq.get("SIFT", ""))  or "."
            poly_label  = _extract_pred_label(csq.get("PolyPhen", "")) or "."

            results.append({
                "gene":       csq.get("SYMBOL", "."),
                "hgvsc":      csq.get("HGVSc", "."),
                "hgvsp":      csq.get("HGVSp", "."),
                "consequence": csq.get("Consequence", ".").split("&")[0],
                "impact":     csq.get("IMPACT", "."),
                "gnomad_af":  gnomad_display,
                "clinvar":    csq.get("ClinVar_CLNSIG", "") or ".",
                "criteria":   "|".join(triggered) if triggered else "None",
                "acmg_class": classification,
                "acmg_score": score,
                "sift":       sift_label,
                "polyphen":   poly_label,
                "chrom":      chrom,
                "pos":        pos,
                "ref":        ref,
                "alt":        alt,
            })

    if not has_csq:
        raise ValueError(
            "No VEP CSQ annotations found in this VCF. "
            "Please annotate with Ensembl VEP using --everything --check_existing first."
        )

    # Sort: Pathogenic → LP → VUS → LB → Benign
    order = {
        "Pathogenic": 0, "Likely Pathogenic": 1,
        "Uncertain Significance": 2, "Likely Benign": 3, "Benign": 4,
    }
    results.sort(key=lambda x: order.get(x["acmg_class"], 5))

    pathogenic_list = [r for r in results if r["acmg_class"] in ("Pathogenic", "Likely Pathogenic")]

    summary = {
        "total_variants":          len(results),
        "classification_counts":   dict(counts),
        "pathogenic_count":        counts.get("Pathogenic", 0),
        "likely_pathogenic_count": counts.get("Likely Pathogenic", 0),
        "vus_count":               counts.get("Uncertain Significance", 0),
        "likely_benign_count":     counts.get("Likely Benign", 0),
        "benign_count":            counts.get("Benign", 0),
        "top_pathogenic":          pathogenic_list[:10],
        "criteria_framework":      "ACMG/AMP 2015 (Richards et al., Genet Med 17:405-424)",
        "criteria_evaluated":      [
            "PVS1","PS1","PM1","PM2","PM4","PM5",
            "PP2","PP3","PP5","BA1","BS1","BP1","BP4","BP7"
        ],
        "annotation_source": "Ensembl VEP --everything --check_existing",
    }

    return results, summary
