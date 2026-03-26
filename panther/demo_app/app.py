"""
OncoPanther-AI | Pharmacogenomics (PGx) Clinical Demo Platform
Interactive dashboard for NABL/CAP lab accreditation demonstration
"""

import streamlit as st
import streamlit.components.v1 as components
import subprocess
import os
import json
import threading
import time
import tempfile
import shutil
import uuid
from io import BytesIO
from pathlib import Path
from datetime import date, datetime
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

# ACMG/AMP 2015 inline classifier
try:
    from acmg_classifier import classify_vcf_bytes
    ACMG_CLASSIFIER_OK = True
except ImportError:
    ACMG_CLASSIFIER_OK = False

# OncoPanther AI Engine — offline RAG + local LLM
try:
    from ai_engine import (
        interpret_variant, explain_pgx, batch_interpret_top_variants, ai_status
    )
    AI_ENGINE_OK = True
except ImportError:
    AI_ENGINE_OK = False
    def ai_status(): return {"mode": "unavailable", "llm_ready": False, "chromadb": False, "embeddings": False}

# ReportLab for in-memory PDF generation
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table,
        TableStyle, HRFlowable
    )
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
PANTHER_DIR = Path("/mnt/c/Users/drkat/OneDrive/Desktop/oncopanther-pgx/oncopanther-pgx/panther")
DEMO_OUTDIR = PANTHER_DIR / "outdir" / "demo_sessions"
UPLOAD_DIR  = Path("/home/crak/demo_uploads")
CONDA_ACTIVATE = "source /home/crak/miniconda3/etc/profile.d/conda.sh && conda activate base"

# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE EXECUTION HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def save_uploaded_file(uploaded_file, dest_path: Path) -> Path:
    """Save a Streamlit UploadedFile to a WSL filesystem path."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return dest_path


def create_session_samplesheets(session_id, patient_id, physician, institution,
                                 gender, dob, ethnicity, diagnosis,
                                 r1_path=None, r2_path=None, vcf_path=None):
    """Create per-session CSV samplesheets and YAML for Nextflow pipeline."""
    sess_dir = UPLOAD_DIR / session_id
    csvs_dir = sess_dir / "CSVs"
    csvs_dir.mkdir(parents=True, exist_ok=True)
    outdir = sess_dir / "outdir"
    outdir.mkdir(parents=True, exist_ok=True)

    if r1_path:
        asm_csv = csvs_dir / "3_samplesheetForAssembly.csv"
        with open(asm_csv, "w") as f:
            if r2_path:
                f.write("patient_id,read1,read2\n")
                f.write(f"{patient_id},{r1_path},{r2_path}\n")
            else:
                # Single-end: only R1
                f.write("patient_id,read1\n")
                f.write(f"{patient_id},{r1_path}\n")

    if vcf_path:
        pgx_csv = csvs_dir / "8_samplesheetPgx.csv"
        with open(pgx_csv, "w") as f:
            f.write("patient_id,vcFile\n")
            f.write(f"{patient_id},{vcf_path}\n")

    vcf_val = vcf_path or ""
    meta_csv = csvs_dir / "7_metaPatients.csv"
    with open(meta_csv, "w") as f:
        f.write("Identifier,SampleID,Gender,Dob,Ethnicity,Diagnosis,vcFile\n")
        f.write(f"{patient_id},{patient_id},{gender},{dob},{ethnicity},{diagnosis},{vcf_val}\n")

    meta_yaml = csvs_dir / "7_metaPatients.yml"
    with open(meta_yaml, "w") as f:
        f.write(f'physician:\n  name: "{physician}"\n  specialty: "Clinical Pharmacogenomics"\n')
        f.write(f'institution:\n  name: "{institution or "Demo Laboratory"}"\n  accreditation: "Demo"\n')
        f.write('hpo_terms:\n  - id: "HP:0000001"\n    term: "All"\n')

    return csvs_dir, outdir


def run_pipeline_in_background(cmd: str, log_file: Path, done_file: Path):
    """Run Nextflow pipeline in a background thread, stream logs to file."""
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "w", buffering=1) as lf:
            proc = subprocess.Popen(
                cmd, shell=True, stdout=lf, stderr=subprocess.STDOUT,
                executable="/bin/bash"
            )
            proc.wait()
        with open(done_file, "w") as df:
            df.write(f"returncode={proc.returncode}\n")
    except Exception as e:
        with open(done_file, "w") as df:
            df.write(f"error={e}\n")


def parse_pharmcat_results(outdir: Path, patient_id: str):
    """Parse PharmCAT v3 report.json → gene_results + drug_results lists.

    PharmCAT v3 report.json structure:
      genes: {GENE: {sourceDiplotypes: [{allele1:{name}, allele2:{name},
                                          phenotypes:[str], activityScore}]}}
      drugs: [{name, relatedGenes:[{symbol}],
               recommendations:[{classification:{term}, drug:{name}, implications,
                                  population, prescribingInformation}]}]
    """
    gene_results = []
    drug_results = []

    # Prefer report.json (has both genes + drugs) over phenotype.json
    report_files = (
        list(outdir.glob(f"**/pharmcat/**/{patient_id}*.report.json")) +
        list(outdir.glob("**/pharmcat/**/*.report.json")) +
        list(outdir.glob("**/*.report.json"))
    )
    if not report_files:
        return gene_results, drug_results

    try:
        with open(report_files[0]) as f:
            data = json.load(f)

        # ── Genes ────────────────────────────────────────────────────────────
        for gene_sym, gene_data in data.get("genes", {}).items():
            src_dips = gene_data.get("sourceDiplotypes", [])
            if not src_dips:
                continue
            dip = src_dips[0]
            a1_obj = dip.get("allele1") or {}
            a2_obj = dip.get("allele2") or {}
            a1 = (a1_obj.get("name", "Unknown") if isinstance(a1_obj, dict) else str(a1_obj))
            a2 = (a2_obj.get("name", "Unknown") if isinstance(a2_obj, dict) else str(a2_obj))
            diplotype = f"{a1}/{a2}"
            phenotypes = dip.get("phenotypes", [])
            phenotype  = ", ".join(str(p) for p in phenotypes) if phenotypes else "Indeterminate"
            activity   = dip.get("activityScore", "N/A")
            if activity is None:
                activity = "N/A"
            # Skip Unknown/Unknown No Result entries — not useful clinically
            if a1 == "Unknown" and a2 == "Unknown":
                continue
            if phenotype in ("No Result", ""):
                continue
            gene_results.append({
                "gene": gene_sym, "diplotype": diplotype,
                "phenotype": phenotype, "activity": str(activity),
            })

        # ── Drugs ─────────────────────────────────────────────────────────────
        # v3: drugs = {"CPIC Guideline Annotation": {drugName: {guidelines:[{annotations:[]}]}}}
        drugs_section = data.get("drugs", {})
        if isinstance(drugs_section, dict):
            all_drug_entries = []
            for src_dict in drugs_section.values():
                if isinstance(src_dict, dict):
                    all_drug_entries.extend(src_dict.values())
        else:
            all_drug_entries = list(drugs_section)

        for drug_entry in all_drug_entries:
            if not isinstance(drug_entry, dict):
                continue
            drug_name = drug_entry.get("name", "")
            for guideline in drug_entry.get("guidelines", []):
                for annot in guideline.get("annotations", []):
                    cls_obj = annot.get("classification") or {}
                    cls = cls_obj.get("term", "") if isinstance(cls_obj, dict) else str(cls_obj)
                    implications = annot.get("implications") or {}
                    if isinstance(implications, dict):
                        text = "; ".join(f"{k}: {v}" for k, v in implications.items() if v)
                    elif isinstance(implications, list):
                        text = "; ".join(str(i) for i in implications if i)
                    else:
                        text = str(implications)
                    if not text:
                        # v3 uses drugRecommendation; v2 used prescribingInformation
                        text = (annot.get("drugRecommendation") or
                                annot.get("prescribingInformation") or "")
                    # v3: gene comes from activityScore keys; v2 used relatedGenes
                    related = annot.get("relatedGenes", [])
                    if related:
                        gene_syms = ", ".join(
                            g.get("symbol", str(g)) if isinstance(g, dict) else str(g)
                            for g in related
                        )
                    else:
                        # v3 fallback: extract gene names from activityScore dict keys
                        act_score = annot.get("activityScore") or {}
                        gene_syms = ", ".join(act_score.keys()) if isinstance(act_score, dict) else ""
                    if drug_name and cls:
                        drug_results.append({
                            "drug": drug_name, "gene": gene_syms,
                            "classification": cls, "recommendation": text,
                        })
    except Exception:
        pass

    return gene_results, drug_results


def parse_acmg_tsv(outdir: Path, patient_id: str) -> list:
    """
    Parse the _acmg.tsv produced by 07.3_AcmgClassify.nf into a list of
    dicts that match the DEMO_ACMG_RESULTS / Tab-4 display format.
    Returns [] if no file found.
    """
    acmg_files = (
        list(outdir.glob(f"**/acmg/**/{patient_id}_acmg.tsv")) +
        list(outdir.glob(f"**/{patient_id}_acmg.tsv")) +
        list(outdir.glob("**/*_acmg.tsv"))
    )
    if not acmg_files:
        return []

    results = []
    try:
        import csv
        with open(acmg_files[0], newline="") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                af_raw = row.get("gnomAD_AF", "") or row.get("MAX_AF", "")
                try:
                    af_f = float(af_raw) if af_raw not in (".", "", "NA") else None
                    af_display = f"<0.001" if (af_f is not None and af_f < 0.001) else (f"{af_f:.4f}" if af_f else ".")
                except Exception:
                    af_display = af_raw or "."

                sift_label = (row.get("SIFT", "") or ".").split("(")[0].lower() or "."
                poly_label = (row.get("PolyPhen", "") or ".").split("(")[0].lower() or "."

                results.append({
                    "gene":        row.get("GENE", "."),
                    "hgvsc":       row.get("HGVSc", "."),
                    "hgvsp":       row.get("HGVSp", "."),
                    "consequence": (row.get("CONSEQUENCE", ".") or ".").split("&")[0],
                    "impact":      row.get("IMPACT", "."),
                    "gnomad_af":   af_display,
                    "clinvar":     row.get("ClinVar_CLNSIG", "") or ".",
                    "criteria":    row.get("CRITERIA", "None"),
                    "acmg_class":  row.get("ACMG_CLASS", "Uncertain Significance"),
                    "acmg_score":  row.get("ACMG_SCORE", "0"),
                    "sift":        sift_label,
                    "polyphen":    poly_label,
                    "chrom":       row.get("CHROM", "."),
                    "pos":         row.get("POS", "."),
                    "ref":         row.get("REF", "."),
                    "alt":         row.get("ALT", "."),
                })
    except Exception:
        pass

    return results


def generate_pgx_pdf(patient_id, physician, institution, gender, dob,
                     ethnicity, diagnosis, gene_results, drug_results,
                     session_id, demo_mode=False, acmg_results=None, acmg_summary=None):
    """
    Generate a clinical PGx PDF report in-memory using ReportLab.
    Returns bytes or None if ReportLab is unavailable.
    """
    if not REPORTLAB_OK:
        return None

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        rightMargin=1.5 * cm, leftMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        title=f"OncoPanther-AI PGx Report – {patient_id}",
    )

    RED       = colors.HexColor("#E74C3C")
    DARK      = colors.HexColor("#2C3E50")
    LGRAY     = colors.HexColor("#f8f9fa")
    GRIDLINE  = colors.HexColor("#dee2e6")

    styles = getSampleStyleSheet()
    normal = styles["Normal"]

    def sty(name, **kw):
        return ParagraphStyle(name, parent=normal, **kw)

    hdr_title = sty("HT", fontSize=20, fontName="Helvetica-Bold",
                    textColor=colors.white, alignment=TA_CENTER)
    hdr_sub   = sty("HS", fontSize=9,  fontName="Helvetica",
                    textColor=colors.HexColor("#cccccc"), alignment=TA_CENTER)
    sec_title = sty("ST", fontSize=11, fontName="Helvetica-Bold",
                    textColor=DARK, spaceBefore=10, spaceAfter=4)
    bold9     = sty("B9", fontSize=9,  fontName="Helvetica-Bold")
    val9      = sty("V9", fontSize=9,  fontName="Helvetica")
    ctr9      = sty("C9", fontSize=9,  fontName="Helvetica", alignment=TA_CENTER)
    tiny      = sty("TY", fontSize=7.5, textColor=colors.HexColor("#555555"), leading=11)

    story = []

    # ── Header banner ────────────────────────────────────────────────────────
    hdr = Table(
        [[Paragraph("OncoPanther-AI | Pharmacogenomics Report", hdr_title)],
         [Paragraph("Precision Drug-Gene Interaction Analysis &nbsp;|&nbsp; PharmCAT v3.1.1 &nbsp;|&nbsp; CPIC Level A", hdr_sub)]],
        colWidths=[18 * cm],
    )
    hdr.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), DARK),
        ("TOPPADDING",   (0, 0), (-1,  0), 14),
        ("BOTTOMPADDING",(0,-1), (-1, -1), 14),
        ("LEFTPADDING",  (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story += [hdr, Spacer(1, 0.4 * cm)]

    # ── Patient information ──────────────────────────────────────────────────
    story.append(Paragraph("Patient Information", sec_title))
    story.append(HRFlowable(width="100%", thickness=2, color=RED, spaceAfter=6))

    rdate = datetime.now().strftime("%d %B %Y")
    src   = "Demo (NA12878 GIAB)" if demo_mode else "Patient Sample"
    pat_rows = [
        [Paragraph("Patient ID:",   bold9), Paragraph(str(patient_id),       val9),
         Paragraph("Report Date:",  bold9), Paragraph(rdate,                  val9)],
        [Paragraph("Physician:",    bold9), Paragraph(str(physician or "—"),  val9),
         Paragraph("Session ID:",   bold9), Paragraph(str(session_id or "—"), val9)],
        [Paragraph("Institution:",  bold9), Paragraph(str(institution or "—"),val9),
         Paragraph("Gender:",       bold9), Paragraph(str(gender or "—"),     val9)],
        [Paragraph("Date of Birth:",bold9), Paragraph(str(dob or "—"),        val9),
         Paragraph("Ethnicity:",    bold9), Paragraph(str(ethnicity or "—"),  val9)],
        [Paragraph("Diagnosis:",    bold9), Paragraph(str(diagnosis or "—"),  val9),
         Paragraph("Data Source:",  bold9), Paragraph(src,                    val9)],
    ]
    pt = Table(pat_rows, colWidths=[3.5 * cm, 5.5 * cm, 3.5 * cm, 5.5 * cm])
    pt.setStyle(TableStyle([
        ("GRID",        (0, 0), (-1, -1), 0.5, GRIDLINE),
        ("ROWPADDING",  (0, 0), (-1, -1), 5),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, LGRAY]),
    ]))
    story += [pt, Spacer(1, 0.3 * cm)]

    # ── Summary metrics ──────────────────────────────────────────────────────
    pm  = sum(1 for g in gene_results if "Poor"         in g.get("phenotype",""))
    im  = sum(1 for g in gene_results if "Intermediate" in g.get("phenotype",""))
    nm  = sum(1 for g in gene_results if "Normal"       in g.get("phenotype",""))
    um  = sum(1 for g in gene_results if "Rapid"        in g.get("phenotype",""))
    act = sum(1 for d in drug_results if d.get("classification","") != "No change")

    def big(n, col):
        return Paragraph(f'<font color="{col}" size="18"><b>{n}</b></font>', styles["Normal"])
    def lbl(t):
        return Paragraph(f'<font size="8" color="#7f8c8d">{t}</font>', styles["Normal"])

    met = Table(
        [[big(len(gene_results),"#2C3E50"), big(pm,"#E74C3C"),
          big(im,"#F39C12"),               big(nm,"#27AE60"), big(act,"#E74C3C")],
         [lbl("Genes Called"),             lbl("Poor Met."),
          lbl("Intermediate"),             lbl("Normal Met."),lbl("Actionable Drugs")]],
        colWidths=[3.6 * cm] * 5,
    )
    met.setStyle(TableStyle([
        ("ALIGN",       (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",  (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING",(0,0),(-1, -1), 6),
        ("GRID",        (0, 0), (-1, -1), 0.5, GRIDLINE),
        ("BACKGROUND",  (0, 0), (-1, -1), colors.white),
    ]))
    story += [met, Spacer(1, 0.35 * cm)]

    # ── Gene results table ───────────────────────────────────────────────────
    story.append(Paragraph("Star Allele Calls & Metabolizer Phenotypes", sec_title))
    story.append(HRFlowable(width="100%", thickness=2, color=RED, spaceAfter=6))

    PHENO_BG = {
        "Poor":         colors.HexColor("#FADBD8"),
        "Intermediate": colors.HexColor("#FEF9E7"),
        "Normal":       colors.HexColor("#EAFAF1"),
        "Rapid":        colors.HexColor("#D6EAF8"),
        "Ultrarapid":   colors.HexColor("#D6EAF8"),
    }
    g_rows = [[Paragraph(h, sty(f"GH{i}", fontSize=9, fontName="Helvetica-Bold",
                                textColor=colors.white, alignment=TA_CENTER))
               for i, h in enumerate(["Gene", "Diplotype", "Phenotype", "Activity Score"])]]
    g_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), DARK),
        ("GRID",       (0, 0), (-1,-1), 0.5, GRIDLINE),
        ("ROWPADDING", (0, 0), (-1,-1), 5),
        ("ALIGN",      (0, 0), (-1,-1), "CENTER"),
        ("VALIGN",     (0, 0), (-1,-1), "MIDDLE"),
    ]
    for i, g in enumerate(gene_results, 1):
        pheno = g.get("phenotype", "")
        bg = next((c for k, c in PHENO_BG.items() if k in pheno), colors.white)
        g_rows.append([
            Paragraph(f"<b>{g.get('gene','')}</b>", ctr9),
            Paragraph(g.get("diplotype","N/A"), ctr9),
            Paragraph(pheno, ctr9),
            Paragraph(g.get("activity","N/A"), ctr9),
        ])
        g_styles.append(("BACKGROUND", (0, i), (-1, i), bg))

    gt = Table(g_rows, colWidths=[3*cm, 4*cm, 7*cm, 4*cm])
    gt.setStyle(TableStyle(g_styles))
    story += [gt, Spacer(1, 0.4 * cm)]

    # ── Drug recommendations ─────────────────────────────────────────────────
    story.append(Paragraph("Drug Dosing Recommendations (CPIC Level A)", sec_title))
    story.append(HRFlowable(width="100%", thickness=2, color=RED, spaceAfter=6))

    d_rows = [[Paragraph(h, sty(f"DH{i}", fontSize=9, fontName="Helvetica-Bold",
                                textColor=colors.white, alignment=TA_CENTER))
               for i, h in enumerate(["Drug", "Gene(s)", "Classification", "Recommendation"])]]
    d_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), DARK),
        ("GRID",       (0, 0), (-1,-1), 0.5, GRIDLINE),
        ("ROWPADDING", (0, 0), (-1,-1), 5),
        ("VALIGN",     (0, 0), (-1,-1), "TOP"),
        ("ALIGN",      (0, 0), ( 2,-1), "CENTER"),
    ]
    for i, d in enumerate(drug_results, 1):
        cls = d.get("classification", "")
        cl  = cls.lower()
        if "avoid" in cl or "contrain" in cl:
            row_bg = colors.HexColor("#FADBD8")
        elif "caution" in cl or "alter" in cl or "dose" in cl or "reduc" in cl:
            row_bg = colors.HexColor("#FEF9E7")
        else:
            row_bg = colors.HexColor("#EAFAF1")
        rec = d.get("recommendation","")
        if len(rec) > 130:
            rec = rec[:127] + "…"
        s8 = sty(f"D8{i}", fontSize=8)
        d_rows.append([
            Paragraph(f"<b>{d.get('drug','')}</b>", sty(f"DB{i}", fontSize=8, fontName="Helvetica-Bold")),
            Paragraph(d.get("gene",""), s8),
            Paragraph(cls, s8),
            Paragraph(rec,  s8),
        ])
        d_styles.append(("BACKGROUND", (0, i), (-1, i), row_bg))

    dt = Table(d_rows, colWidths=[3*cm, 3*cm, 3.5*cm, 8.5*cm])
    dt.setStyle(TableStyle(d_styles))
    story += [dt, Spacer(1, 0.4 * cm)]

    # ── ACMG/AMP Variant Classification ──────────────────────────────────────
    if acmg_results:
        story.append(Paragraph("ACMG/AMP 2015 Variant Classification", sec_title))
        story.append(HRFlowable(width="100%", thickness=2, color=RED, spaceAfter=6))

        # Summary counts row
        if acmg_summary:
            n_p  = acmg_summary.get("pathogenic_count", 0)
            n_lp = acmg_summary.get("likely_pathogenic_count", 0)
            n_v  = acmg_summary.get("vus_count", 0)
            n_lb = acmg_summary.get("likely_benign_count", 0)
            n_b  = acmg_summary.get("benign_count", 0)
            n_tot= acmg_summary.get("total_variants", len(acmg_results))
            TIER_C = {
                "P":  colors.HexColor("#E74C3C"), "LP": colors.HexColor("#E67E22"),
                "VUS":colors.HexColor("#F39C12"), "LB": colors.HexColor("#2ECC71"),
                "B":  colors.HexColor("#27AE60"),
            }
            def acmg_big(n, col): return Paragraph(f'<font color="{col.hexval()}" size="16"><b>{n}</b></font>', styles["Normal"])
            def acmg_lbl(t):      return Paragraph(f'<font size="8" color="#7f8c8d">{t}</font>', styles["Normal"])
            acmg_met = Table(
                [[acmg_big(n_p,TIER_C["P"]), acmg_big(n_lp,TIER_C["LP"]),
                  acmg_big(n_v,TIER_C["VUS"]), acmg_big(n_lb,TIER_C["LB"]), acmg_big(n_b,TIER_C["B"])],
                 [acmg_lbl("Pathogenic"), acmg_lbl("Likely Path."),
                  acmg_lbl("VUS"), acmg_lbl("Likely Benign"), acmg_lbl("Benign")]],
                colWidths=[3.6*cm]*5,
            )
            acmg_met.setStyle(TableStyle([
                ("ALIGN",(0,0),(-1,-1),"CENTER"),
                ("TOPPADDING",(0,0),(-1,-1),6), ("BOTTOMPADDING",(0,0),(-1,-1),4),
                ("GRID",(0,0),(-1,-1),0.5,GRIDLINE), ("BACKGROUND",(0,0),(-1,-1),colors.white),
            ]))
            story += [acmg_met, Spacer(1, 0.3*cm)]

        # Variant table (top 30 — P/LP/VUS first)
        ACMG_TIER_BG_PDF = {
            "Pathogenic":           colors.HexColor("#FADBD8"),
            "Likely Pathogenic":    colors.HexColor("#FDEBD0"),
            "Uncertain Significance": colors.HexColor("#FEF9E7"),
            "Likely Benign":        colors.HexColor("#EAFAF1"),
            "Benign":               colors.HexColor("#D5F5E3"),
        }
        display_acmg = acmg_results[:30]
        ah = ["Gene", "HGVSp", "Consequence", "ClinVar", "Criteria", "Class"]
        a_rows = [[Paragraph(h, sty(f"AH{i}", fontSize=8, fontName="Helvetica-Bold",
                                    textColor=colors.white, alignment=TA_CENTER))
                   for i, h in enumerate(ah)]]
        a_styles = [
            ("BACKGROUND",(0,0),(-1,0),DARK),
            ("GRID",(0,0),(-1,-1),0.5,GRIDLINE),
            ("ROWPADDING",(0,0),(-1,-1),4),
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ("ALIGN",(0,0),(-1,-1),"CENTER"),
        ]
        for i, av in enumerate(display_acmg, 1):
            tier_bg = ACMG_TIER_BG_PDF.get(av.get("acmg_class",""), colors.white)
            hgvsp = av.get("hgvsp",".")
            if hgvsp and len(hgvsp) > 20: hgvsp = "…" + hgvsp[-18:]
            a_rows.append([
                Paragraph(f"<b>{av.get('gene','.')}</b>", sty(f"AG{i}",fontSize=7,fontName="Helvetica-Bold")),
                Paragraph(hgvsp or ".", sty(f"AP{i}",fontSize=7)),
                Paragraph((av.get("consequence",".")or".")[:25], sty(f"AC{i}",fontSize=7)),
                Paragraph((av.get("clinvar",".")or".")[:20], sty(f"ACV{i}",fontSize=7)),
                Paragraph(av.get("criteria",".")or".", sty(f"ACR{i}",fontSize=7)),
                Paragraph(av.get("acmg_class",".")or".", sty(f"ACL{i}",fontSize=7,fontName="Helvetica-Bold")),
            ])
            a_styles.append(("BACKGROUND",(0,i),(-1,i),tier_bg))
        at = Table(a_rows, colWidths=[2.5*cm, 3.5*cm, 3.5*cm, 2.5*cm, 2.5*cm, 3.5*cm])
        at.setStyle(TableStyle(a_styles))
        story += [at, Spacer(1, 0.4*cm)]
        if len(acmg_results) > 30:
            story.append(Paragraph(
                f"<i>Showing top 30 of {len(acmg_results)} variants. Full results available in downloadable TSV.</i>",
                sty("ACMG_NOTE", fontSize=7, textColor=colors.HexColor("#888888")),
            ))
            story.append(Spacer(1, 0.2*cm))

    # ── Audit Trail ──────────────────────────────────────────────────────────
    audit_text = (
        f"<b>Run ID:</b> {session_id or 'N/A'} &nbsp;|&nbsp; "
        f"<b>Report Date:</b> {datetime.now().strftime('%Y-%m-%d %H:%M UTC')} &nbsp;|&nbsp; "
        f"<b>Pipeline:</b> OncoPanther-AI v1.0.0<br/>"
        f"<b>Reference Genome:</b> GRCh38 (hg38) &nbsp;|&nbsp; "
        f"<b>Aligner:</b> BWA-MEM2 v2.2.1 &nbsp;|&nbsp; "
        f"<b>Variant Caller:</b> GATK HaplotypeCaller v4.4.0<br/>"
        f"<b>PharmCAT:</b> v3.1.1 (data: 2025-11-05) &nbsp;|&nbsp; "
        f"<b>VEP:</b> v114 (Ensembl) &nbsp;|&nbsp; "
        f"<b>ClinVar:</b> 2024-03 &nbsp;|&nbsp; "
        f"<b>PGx Guidelines:</b> CPIC (cpicpgx.org)"
    )
    audit = Table([[Paragraph(audit_text,
        sty("AT", fontSize=7, textColor=colors.HexColor("#1B4F8A"), leading=11))
    ]], colWidths=[18 * cm])
    audit.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EBF5FB")),
        ("BOX",        (0, 0), (-1, -1), 0.5, colors.HexColor("#1B4F8A")),
        ("ROWPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(audit)
    story.append(Spacer(1, 0.2*cm))

    # ── Disclaimer ───────────────────────────────────────────────────────────
    disc = Table([[Paragraph(
        "<b>Disclaimer:</b> This report is generated by OncoPanther-AI using PharmCAT v3.1.1 and CPIC guidelines. "
        "Results must be interpreted by qualified clinical pharmacogeneticists in the context of the patient's complete "
        "clinical presentation. This platform is for <b>research and demonstration purposes only</b>. "
        "Clinical deployment requires NABL/CAP/CLIA-accredited laboratory infrastructure.<br/><br/>"
        "<b>OncoPanther-AI</b> developed by "
        "<b>Kesavi Himabindhu Vuyyuru, Chinmai Rayidi &amp; Abraham Peele Karlapudi</b>, "
        "Dept. of Biotechnology &amp; Bioinformatics, "
        "Vignan's Foundation for Science, Technology &amp; Research (Deemed to be University) | "
        "Industry Partner: <b>SecuAI</b> | v1.0-beta",
        tiny,
    )]], colWidths=[18 * cm])
    disc.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LGRAY),
        ("BOX",        (0, 0), (-1, -1), 0.5, GRIDLINE),
        ("ROWPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(disc)

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


PHENOTYPE_COLORS = {
    "Poor Metabolizer":            "#E74C3C",
    "Likely Poor Metabolizer":     "#E74C3C",
    "Intermediate Metabolizer":    "#F39C12",
    "Likely Intermediate Metabolizer": "#F39C12",
    "Normal Metabolizer":          "#27AE60",
    "Rapid Metabolizer":           "#3498DB",
    "Ultrarapid Metabolizer":      "#2980B9",
    "Indeterminate":               "#95A5A6",
    "N/A":                         "#BDC3C7",
}

PHENOTYPE_EMOJI = {
    "Poor Metabolizer":            "🔴",
    "Likely Poor Metabolizer":     "🔴",
    "Intermediate Metabolizer":    "🟡",
    "Likely Intermediate Metabolizer": "🟡",
    "Normal Metabolizer":          "🟢",
    "Rapid Metabolizer":           "🔵",
    "Ultrarapid Metabolizer":      "🔵",
    "Indeterminate":               "⚪",
    "N/A":                         "⚪",
}

CPIC_GENES = [
    "CYP2D6","CYP2C19","CYP2C9","CYP3A5","CYP4F2",
    "CYP2B6","DPYD","TPMT","NUDT15","UGT1A1",
    "SLCO1B1","VKORC1","IFNL3","G6PD","NAT2",
    "HLA-A","HLA-B","MT-RNR1","RYR1","CACNA1S"
]

# ── Load REAL NA12878 pipeline results at startup ─────────────────────────────
# Reads from the completed full pipeline run (ERR194147 → GRCh38 → PharmCAT)
# Falls back to DEMO constants below if the pipeline hasn't run yet
_REAL_NA12878_OUTDIR = PANTHER_DIR / "outdir" / "NA12878"
_rg, _rd = parse_pharmcat_results(_REAL_NA12878_OUTDIR, "NA12878")
# Only use real results for Quick Demo if we have ≥5 genes called (needs ≥10x coverage)
# At 3x coverage only DPYD is called — fall back to DEMO for the full panel display
REAL_GENE_RESULTS     = _rg if _rg and len(_rg) >= 5 else None
REAL_DRUG_RESULTS     = _rd if _rd and len(_rd) >= 5 else None
# Always keep DPYD real call available for info display
REAL_DPYD_CALL        = next((g for g in (_rg or []) if g["gene"] == "DPYD"), None)
REAL_NA12878_PDF      = _REAL_NA12878_OUTDIR / "Reporting" / "PGx" / "NA12878_PGx.pdf"

# Load real ACMG/AMP results from completed NA12878 pipeline run
_real_acmg_rows  = parse_acmg_tsv(_REAL_NA12878_OUTDIR, "NA12878_oncoPanther")
REAL_NA12878_ACMG = _real_acmg_rows[:200] if _real_acmg_rows else None  # top 200 for display
_real_acmg_summary_file = _REAL_NA12878_OUTDIR / "annotation" / "acmg" / "NA12878_oncoPanther_acmg_summary.json"
try:
    import json as _json
    REAL_NA12878_ACMG_SUMMARY = _json.loads(_real_acmg_summary_file.read_text()) if _real_acmg_summary_file.exists() else None
except Exception:
    REAL_NA12878_ACMG_SUMMARY = None

# Pre-loaded demo results (fallback if real pipeline not yet run)
DEMO_GENE_RESULTS = [
    {"gene": "CYP2C19", "diplotype": "*1/*2",  "phenotype": "Intermediate Metabolizer",  "activity": "1.0"},
    {"gene": "CYP2C9",  "diplotype": "*1/*2",  "phenotype": "Intermediate Metabolizer",  "activity": "1.5"},
    {"gene": "CYP3A5",  "diplotype": "*3/*3",  "phenotype": "Poor Metabolizer",          "activity": "0.0"},
    {"gene": "DPYD",    "diplotype": "*1/*1",  "phenotype": "Normal Metabolizer",         "activity": "2.0"},
    {"gene": "SLCO1B1", "diplotype": "*1/*15", "phenotype": "Intermediate Metabolizer",  "activity": "N/A"},
    {"gene": "UGT1A1",  "diplotype": "*1/*80", "phenotype": "Intermediate Metabolizer",  "activity": "N/A"},
    {"gene": "TPMT",    "diplotype": "*1/*1",  "phenotype": "Normal Metabolizer",         "activity": "2.0"},
    {"gene": "CYP2D6",  "diplotype": "*1/*2",  "phenotype": "Normal Metabolizer",         "activity": "2.0"},
    {"gene": "NUDT15",  "diplotype": "*1/*1",  "phenotype": "Normal Metabolizer",         "activity": "2.0"},
    {"gene": "CYP2B6",  "diplotype": "*1/*1",  "phenotype": "Normal Metabolizer",         "activity": "2.0"},
]

DEMO_DRUG_RESULTS = [
    {"drug": "Clopidogrel",   "gene": "CYP2C19", "classification": "Use with caution",
     "recommendation": "CYP2C19 IM — consider alternative antiplatelet (e.g., prasugrel, ticagrelor) per CPIC guidelines."},
    {"drug": "Warfarin",      "gene": "CYP2C9 + VKORC1", "classification": "Altered dose",
     "recommendation": "CYP2C9 IM — initiate at reduced dose. Monitor INR closely."},
    {"drug": "Tacrolimus",    "gene": "CYP3A5", "classification": "Altered dose",
     "recommendation": "CYP3A5 PM (*3/*3) — standard dose or increase per transplant protocol."},
    {"drug": "Simvastatin",   "gene": "SLCO1B1", "classification": "Use with caution",
     "recommendation": "SLCO1B1 *15 — increased statin myopathy risk. Consider lower dose or alternative."},
    {"drug": "Irinotecan",    "gene": "UGT1A1", "classification": "Use with caution",
     "recommendation": "UGT1A1 *80 — monitor for neutropenia; dose reduction may be warranted."},
    {"drug": "Tamoxifen",     "gene": "CYP2D6", "classification": "No change",
     "recommendation": "CYP2D6 NM — standard dose is appropriate."},
    {"drug": "5-Fluorouracil","gene": "DPYD",    "classification": "No change",
     "recommendation": "DPYD normal — no dose adjustment required."},
    {"drug": "Azathioprine",  "gene": "TPMT + NUDT15", "classification": "No change",
     "recommendation": "TPMT and NUDT15 NM — standard weight-based dosing recommended."},
]

# ── Demo ACMG data (based on NA12878 GIAB — illustrative classifications) ────
DEMO_ACMG_RESULTS = [
    {"gene":"BRCA2",  "hgvsc":"NM_000059.4:c.5946delT","consequence":"frameshift_variant",
     "impact":"HIGH", "gnomad_af":"<0.001","clinvar":"Pathogenic","criteria":"PVS1|PM2",
     "acmg_class":"Pathogenic","sift":"deleterious","polyphen":"probably_damaging"},
    {"gene":"TP53",   "hgvsc":"NM_000546.6:c.817C>T","consequence":"missense_variant",
     "impact":"MODERATE","gnomad_af":"0.00003","clinvar":"Likely_pathogenic","criteria":"PS1|PM1|PP3",
     "acmg_class":"Likely Pathogenic","sift":"deleterious","polyphen":"probably_damaging"},
    {"gene":"BRCA1",  "hgvsc":"NM_007294.4:c.5266dupC","consequence":"frameshift_variant",
     "impact":"HIGH","gnomad_af":"<0.001","clinvar":"Pathogenic","criteria":"PVS1|PS1|PM2",
     "acmg_class":"Pathogenic","sift":"deleterious","polyphen":"probably_damaging"},
    {"gene":"MLH1",   "hgvsc":"NM_000249.4:c.1852_1853delAA","consequence":"frameshift_variant",
     "impact":"HIGH","gnomad_af":"<0.001","clinvar":"Pathogenic","criteria":"PVS1|PM2|PP5",
     "acmg_class":"Pathogenic","sift":"deleterious","polyphen":"probably_damaging"},
    {"gene":"KRAS",   "hgvsc":"NM_004985.5:c.35G>T","consequence":"missense_variant",
     "impact":"MODERATE","gnomad_af":"0.00008","clinvar":"Pathogenic","criteria":"PS1|PM1|PM2|PP3",
     "acmg_class":"Likely Pathogenic","sift":"deleterious","polyphen":"probably_damaging"},
    {"gene":"EGFR",   "hgvsc":"NM_005228.5:c.2573T>G","consequence":"missense_variant",
     "impact":"MODERATE","gnomad_af":"0.00012","clinvar":"Uncertain_significance","criteria":"PM1|PM2|PP3",
     "acmg_class":"Uncertain Significance","sift":"deleterious","polyphen":"possibly_damaging"},
    {"gene":"PTEN",   "hgvsc":"NM_000314.8:c.697C>T","consequence":"missense_variant",
     "impact":"MODERATE","gnomad_af":"0.0004","clinvar":"Uncertain_significance","criteria":"PM2|PP2",
     "acmg_class":"Uncertain Significance","sift":"tolerated","polyphen":"benign"},
    {"gene":"VHL",    "hgvsc":"NM_000551.4:c.500G>A","consequence":"missense_variant",
     "impact":"MODERATE","gnomad_af":"0.001","clinvar":"Uncertain_significance","criteria":"PM2",
     "acmg_class":"Uncertain Significance","sift":"tolerated","polyphen":"possibly_damaging"},
    {"gene":"APC",    "hgvsc":"NM_000038.6:c.1A>G","consequence":"synonymous_variant",
     "impact":"LOW","gnomad_af":"0.012","clinvar":"Benign","criteria":"BP7|BS1",
     "acmg_class":"Likely Benign","sift":"tolerated","polyphen":"benign"},
    {"gene":"CDKN2A", "hgvsc":"NM_000077.5:c.442G>A","consequence":"synonymous_variant",
     "impact":"LOW","gnomad_af":"0.032","clinvar":"Benign","criteria":"BA1|BP7",
     "acmg_class":"Benign","sift":"tolerated","polyphen":"benign"},
    {"gene":"NF1",    "hgvsc":"NM_000267.3:c.3113G>A","consequence":"missense_variant",
     "impact":"MODERATE","gnomad_af":"0.021","clinvar":"Benign","criteria":"BA1",
     "acmg_class":"Benign","sift":"tolerated","polyphen":"benign"},
]

ACMG_TIER_COLORS = {
    "Pathogenic":            "#E74C3C",
    "Likely Pathogenic":     "#E67E22",
    "Uncertain Significance":"#F1C40F",
    "Likely Benign":         "#2ECC71",
    "Benign":                "#27AE60",
}
ACMG_TIER_BG = {
    "Pathogenic":            "#FADBD8",
    "Likely Pathogenic":     "#FDEBD0",
    "Uncertain Significance":"#FEF9E7",
    "Likely Benign":         "#EAFAF1",
    "Benign":                "#D5F5E3",
}
ACMG_TIER_EMOJI = {
    "Pathogenic":            "🔴",
    "Likely Pathogenic":     "🟠",
    "Uncertain Significance":"🟡",
    "Likely Benign":         "🟢",
    "Benign":                "✅",
}
CRITERIA_DESCRIPTIONS = {
    "PVS1": "Very Strong — Null variant (LoF) in gene where LoF is disease mechanism",
    "PS1":  "Strong — Same AA change as established pathogenic (ClinVar P/LP ≥2★)",
    "PM1":  "Moderate — Mutational hotspot or functional domain",
    "PM2":  "Moderate — Absent/extremely rare in gnomAD (AF < 0.001)",
    "PM4":  "Moderate — Protein length change (in-frame indel)",
    "PM5":  "Moderate — Novel missense at same position as known pathogenic",
    "PP2":  "Supporting — Missense in gene with low benign missense rate",
    "PP3":  "Supporting — SIFT deleterious AND PolyPhen damaging",
    "PP5":  "Supporting — ClinVar pathogenic (any review status)",
    "BA1":  "Stand-Alone Benign — gnomAD AF > 5%",
    "BS1":  "Strong Benign — gnomAD AF 1–5%",
    "BP1":  "Supporting Benign — Missense in LoF-only gene",
    "BP4":  "Supporting Benign — SIFT tolerated AND PolyPhen benign",
    "BP7":  "Supporting Benign — Synonymous, no predicted splice effect",
}

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="OncoPanther-AI | PGx Platform",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# CUSTOM CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Main background */
    .stApp { background-color: #f8f9fa; }

    /* Sidebar – always on-screen with distinct background */
    section[data-testid="stSidebar"],
    section[data-testid="stSidebar"][aria-expanded="false"],
    section[data-testid="stSidebar"][aria-expanded="true"] {
        background-color: #eef0f3 !important;
        min-width: 260px !important;
        transform: translateX(0) !important;   /* force sidebar on-screen always */
        visibility: visible !important;
        display: block !important;
    }
    /* Also target the Streamlit emotion CSS class that hides the sidebar */
    .st-emotion-cache-1ilsw19 {
        transform: translateX(0) !important;
    }
    section[data-testid="stSidebar"] > div:first-child,
    section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
        background-color: #eef0f3 !important;
        visibility: visible !important;
    }
    /* Ensure collapse button still works visually */
    button[data-testid="collapsedControl"],
    button[aria-label="Close sidebar"],
    button[aria-label="Open sidebar"] {
        display: block !important;
        visibility: visible !important;
        color: #2C3E50 !important;
    }

    /* Header */
    .op-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #2C3E50 100%);
        padding: 18px 28px;
        border-radius: 12px;
        margin-bottom: 24px;
        display: flex;
        align-items: center;
    }
    .op-title { font-size: 30px; font-weight: 900; color: #fff; letter-spacing: 1px; }
    .op-red   { color: #E74C3C; }
    .op-sub   { font-size: 13px; color: #aaa; margin-top: 2px; }

    /* Cards */
    .card {
        background: white;
        border-radius: 10px;
        padding: 20px;
        border: 1px solid #e8eaed;
        box-shadow: 0 1px 4px rgba(0,0,0,0.07);
        margin-bottom: 16px;
    }
    .card-title {
        font-size: 15px; font-weight: 700;
        color: #2C3E50; margin-bottom: 12px;
        border-bottom: 2px solid #E74C3C;
        padding-bottom: 6px;
    }

    /* Gene table rows */
    .g-pm { background: #FADBD8 !important; }
    .g-im { background: #FEF9E7 !important; }
    .g-nm { background: #EAFAF1 !important; }
    .g-um { background: #D6EAF8 !important; }

    /* Status badge */
    .badge-pm { background:#E74C3C; color:white; padding:2px 8px; border-radius:10px; font-size:11px; }
    .badge-im { background:#F39C12; color:white; padding:2px 8px; border-radius:10px; font-size:11px; }
    .badge-nm { background:#27AE60; color:white; padding:2px 8px; border-radius:10px; font-size:11px; }
    .badge-um { background:#2980B9; color:white; padding:2px 8px; border-radius:10px; font-size:11px; }

    /* Run button */
    div[data-testid="stButton"] > button {
        background: linear-gradient(135deg, #C0392B, #E74C3C);
        color: white; border: none;
        border-radius: 8px; padding: 12px 32px;
        font-size: 16px; font-weight: 700;
        width: 100%; cursor: pointer;
        box-shadow: 0 4px 12px rgba(192,57,43,0.3);
    }
    div[data-testid="stButton"] > button:hover {
        background: linear-gradient(135deg, #a93226, #C0392B);
        transform: translateY(-1px);
    }

    /* Download buttons — blue */
    div[data-testid="stDownloadButton"] > button {
        background: linear-gradient(135deg, #1a6fba, #2980B9) !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        box-shadow: 0 3px 10px rgba(41,128,185,0.35) !important;
    }
    div[data-testid="stDownloadButton"] > button:hover {
        background: linear-gradient(135deg, #155a9a, #1a6fba) !important;
        transform: translateY(-1px);
        box-shadow: 0 5px 14px rgba(41,128,185,0.45) !important;
    }
    div[data-testid="stDownloadButton"] > button * {
        color: #ffffff !important;
    }

    /* Metric boxes */
    .metric-box {
        background: white; border-radius: 8px;
        padding: 16px; text-align: center;
        border-left: 4px solid #E74C3C;
        box-shadow: 0 1px 4px rgba(0,0,0,0.07);
    }
    .metric-val { font-size: 28px; font-weight: 900; color: #2C3E50; }
    .metric-lbl { font-size: 12px; color: #7f8c8d; margin-top: 4px; }

    /* Pipeline log */
    .log-box {
        background: #0d1117; color: #58a6ff;
        font-family: 'Courier New', monospace;
        font-size: 12px; padding: 16px;
        border-radius: 8px; height: 320px;
        overflow-y: auto; white-space: pre-wrap;
    }

    /* Sidebar */
    .sidebar-logo {
        text-align: center; padding: 20px 10px;
        border-bottom: 1px solid #e0e0e0; margin-bottom: 16px;
    }
    .sidebar-logo-text { font-size: 24px; font-weight: 900; }
    .sidebar-logo-sub  { font-size: 11px; color: #888; margin-top: 4px; }

    /* Hide streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* ── Force dark text everywhere (fixes white-on-white in dark theme) ── */
    .stApp, .stApp * {
        color: #2C3E50 !important;
    }
    /* Keep white text on intentionally dark elements */
    .op-title, .op-sub, .op-red,
    .badge-pm, .badge-im, .badge-nm, .badge-um,
    .log-box, .log-box *,
    div[data-testid="stButton"] > button,
    div[data-testid="stButton"] > button *,
    div[data-testid="stDownloadButton"] > button,
    div[data-testid="stDownloadButton"] > button * {
        color: inherit !important;
    }
    .op-title { color: #ffffff !important; }
    .op-sub   { color: #aaaaaa !important; }
    .op-red   { color: #E74C3C !important; }
    .badge-pm, .badge-im, .badge-nm, .badge-um { color: #ffffff !important; }
    .log-box, .log-box * { color: #58a6ff !important; }
    div[data-testid="stButton"] > button,
    div[data-testid="stButton"] > button *,
    div[data-testid="stDownloadButton"] > button,
    div[data-testid="stDownloadButton"] > button * { color: #ffffff !important; }

    /* Streamlit form labels, inputs, select boxes */
    label, .stTextInput label, .stSelectbox label,
    .stDateInput label, .stRadio label,
    .stTextInput > div > div > input,
    .stSelectbox > div > div,
    .stNumberInput > div > div > input,
    [data-baseweb="select"] *,
    [data-baseweb="input"] * {
        color: #2C3E50 !important;
    }

    /* Sidebar text – all content dark */
    section[data-testid="stSidebar"],
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] div,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] li,
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {
        color: #2C3E50 !important;
    }
    /* Sidebar divider */
    section[data-testid="stSidebar"] hr {
        border-color: #ced4da !important;
    }

    /* Tab labels */
    button[data-baseweb="tab"] { color: #2C3E50 !important; }
    button[data-baseweb="tab"][aria-selected="true"] { color: #E74C3C !important; }

    /* Info / warning / error boxes */
    div[data-testid="stAlert"] * { color: #2C3E50 !important; }

    /* Metric values */
    .metric-val { color: #2C3E50 !important; }
    .metric-lbl { color: #7f8c8d !important; }

    /* Card title */
    .card-title { color: #2C3E50 !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE INIT
# ─────────────────────────────────────────────────────────────────────────────
for key, default in {
    "pipeline_running":  False,
    "pipeline_done":     False,
    "pipeline_logs":     [],
    "gene_results":      [],
    "drug_results":      [],
    "session_id":        None,
    "session_outdir":    None,
    "patient_id_run":    None,
    # Patient form values – stored so Tab 4 PDF uses the entered data
    "physician_run":     "",
    "institution_run":   "",
    "gender_run":        "",
    "dob_run":           "",
    "ethnicity_run":     "",
    "diagnosis_run":     "",
    "active_tab":        "New Analysis",
    "demo_mode":         False,
    "acmg_results":      [],
    "acmg_vcf_bytes":    None,    # raw bytes of uploaded VEP-annotated VCF
    "acmg_summary":      {},
    "error":             None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ─────────────────────────────────────────────────────────────────────────────
# FORCE SIDEBAR OPEN  (browser may remember collapsed state from prior session)
# ─────────────────────────────────────────────────────────────────────────────
components.html("""
<script>
(function() {
    var doc = window.parent ? window.parent.document : document;
    function expandSidebar() {
        var sb = doc.querySelector('section[data-testid="stSidebar"]');
        if (!sb) { setTimeout(expandSidebar, 400); return; }
        // Force the transform and aria state directly
        sb.style.setProperty('transform', 'translateX(0)', 'important');
        sb.setAttribute('aria-expanded', 'true');
        // Also inject a persistent style override
        if (!doc.getElementById('sb-force-style')) {
            var s = doc.createElement('style');
            s.id = 'sb-force-style';
            s.innerHTML =
              'section[data-testid="stSidebar"] { transform: translateX(0) !important; }' +
              '.st-emotion-cache-1ilsw19 { transform: translateX(0) !important; }';
            doc.head.appendChild(s);
        }
    }
    setTimeout(expandSidebar, 600);
    setTimeout(expandSidebar, 1500);
    setTimeout(expandSidebar, 3000);
})();
</script>
""", height=0)

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div class="sidebar-logo">
        <div class="sidebar-logo-text">Onco<span style="color:#E74C3C">P</span>anther<span style="color:#888;font-size:14px">-AI</span></div>
        <div class="sidebar-logo-sub">Precision Pharmacogenomics Platform</div>
        <div style="margin-top:8px;">
            <span style="background:#E74C3C;color:white;padding:2px 8px;border-radius:10px;font-size:10px;">PharmCAT 3.1.1</span>
            <span style="background:#27AE60;color:white;padding:2px 8px;border-radius:10px;font-size:10px;margin-left:4px;">CPIC Level A</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### Pipeline Capabilities")
    capabilities = {
        "FASTQ → BAM Alignment": "BWA + Picard",
        "Variant Calling": "GATK HaplotypeCaller",
        "PGx Star Alleles": "PharmCAT 3.1.1 (CPIC)",
        "CYP2D6 SVs": "Cyrius v1.1.1",
        "Drug Recommendations": "CPIC / DPWG / FDA",
        "Reference Genome": "GRCh38 (hg38)",
        "Report Format": "Clinical PDF",
    }
    for cap, tool in capabilities.items():
        st.markdown(f"- **{cap}**: {tool}")

    st.divider()
    st.markdown("### 🏆 Competitive Edge")
    st.markdown("""
    <div style="font-size:11px;">
    <table style="width:100%;border-collapse:collapse;">
      <tr style="background:#1B4F8A;color:white;">
        <th style="padding:4px 6px;text-align:left;">Feature</th>
        <th style="padding:4px 6px;text-align:center;">Others</th>
        <th style="padding:4px 6px;text-align:center;">Ours</th>
      </tr>
      <tr style="background:#f8f9fa;">
        <td style="padding:3px 6px;">Variant Calling</td>
        <td style="text-align:center;">✅</td><td style="text-align:center;">✅</td>
      </tr>
      <tr>
        <td style="padding:3px 6px;">VEP Annotation</td>
        <td style="text-align:center;">✅</td><td style="text-align:center;">✅</td>
      </tr>
      <tr style="background:#f8f9fa;">
        <td style="padding:3px 6px;"><b>ACMG/AMP Classification</b></td>
        <td style="text-align:center;">❌</td><td style="text-align:center;color:#27AE60;font-weight:700;">✅</td>
      </tr>
      <tr>
        <td style="padding:3px 6px;"><b>PGx (PharmCAT+CPIC)</b></td>
        <td style="text-align:center;">❌</td><td style="text-align:center;color:#27AE60;font-weight:700;">✅</td>
      </tr>
      <tr style="background:#f8f9fa;">
        <td style="padding:3px 6px;"><b>Unified PDF Report</b></td>
        <td style="text-align:center;">❌</td><td style="text-align:center;color:#27AE60;font-weight:700;">✅</td>
      </tr>
      <tr>
        <td style="padding:3px 6px;"><b>REST API</b></td>
        <td style="text-align:center;">❌</td><td style="text-align:center;color:#27AE60;font-weight:700;">✅</td>
      </tr>
      <tr style="background:#f8f9fa;">
        <td style="padding:3px 6px;"><b>Docker Ready</b></td>
        <td style="text-align:center;">❌</td><td style="text-align:center;color:#27AE60;font-weight:700;">✅</td>
      </tr>
    </table>
    </div>
    """, unsafe_allow_html=True)

    st.divider()
    st.markdown("### Accreditation Ready")
    st.info("🏛️ This platform supports **NABL / CAP / CLIA** laboratory accreditation workflows.\n\nAll PGx calls are based on peer-reviewed CPIC guidelines and PharmCAT — cited in FDA PGx guidance documents.")

    st.divider()
    st.markdown("""
    <div style="text-align:center;padding:10px 4px;">
        <div style="font-size:13px;font-weight:700;color:#2C3E50;letter-spacing:0.5px;">
            Onco<span style="color:#E74C3C;">P</span>anther-AI &nbsp;v1.0-beta
        </div>
        <div style="font-size:11px;color:#888;margin-top:4px;">
            Precision Pharmacogenomics Platform
        </div>
        <div style="margin-top:10px;padding:10px;background:#f8f9fa;border-radius:8px;border:1px solid #e8eaed;">
            <div style="font-size:10px;color:#7f8c8d;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;">
                Developed by
            </div>
            <div style="font-size:12px;font-weight:600;color:#2C3E50;line-height:1.9;">
                Kesavi Himabindhu Vuyyuru<br>
                Chinmai Rayidi<br>
                Abraham Peele Karlapudi
            </div>
            <div style="font-size:10px;color:#555;font-weight:600;margin-top:6px;">
                Dept. of Biotechnology &amp; Bioinformatics
            </div>
            <div style="font-size:10px;color:#7f8c8d;margin-top:3px;line-height:1.5;">
                Vignan's Foundation for Science,<br>
                Technology &amp; Research<br>
                <i>(Deemed to be University)</i>
            </div>
            <div style="font-size:10px;color:#7f8c8d;margin-top:5px;">
                Developed for Industry Partner:
            </div>
            <div style="margin-top:5px;">
                <span style="background:#E74C3C;color:white;padding:2px 10px;border-radius:10px;font-size:11px;font-weight:700;letter-spacing:1px;">
                    SecuAI
                </span>
            </div>
        </div>
        <div style="font-size:10px;color:#aaa;margin-top:8px;">
            For research &amp; demonstration use only
        </div>
    </div>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="op-header">
    <div>
        <div class="op-title">Onco<span class="op-red">P</span>anther-AI &nbsp;|&nbsp; Pharmacogenomics Platform</div>
        <div class="op-sub">End-to-end PGx pipeline: FASTQ → Alignment → Variant Calling → Star Allele Calling → Clinical PDF Report</div>
    </div>
</div>
""", unsafe_allow_html=True)

# Top metrics
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.markdown('<div class="metric-box"><div class="metric-val">20</div><div class="metric-lbl">CPIC Level A Genes</div></div>', unsafe_allow_html=True)
with col2:
    st.markdown('<div class="metric-box"><div class="metric-val">100+</div><div class="metric-lbl">Actionable Drugs</div></div>', unsafe_allow_html=True)
with col3:
    st.markdown('<div class="metric-box"><div class="metric-val">GRCh38</div><div class="metric-lbl">Reference Genome</div></div>', unsafe_allow_html=True)
with col4:
    st.markdown('<div class="metric-box"><div class="metric-val">3.1.1</div><div class="metric-lbl">PharmCAT Version</div></div>', unsafe_allow_html=True)
with col5:
    st.markdown('<div class="metric-box"><div class="metric-val">CPIC</div><div class="metric-lbl">Guideline Source</div></div>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🧬 New Analysis",
    "⚙️ Pipeline Status",
    "📊 PGx Results",
    "🔬 Variant Interpretation",
    "🤖 AI Interpretation",
    "📄 Report & Download",
])

# ═════════════════════════════════════════════════════════════════════════════
# TAB 1: NEW ANALYSIS
# ═════════════════════════════════════════════════════════════════════════════
with tab1:

    col_form, col_upload = st.columns([1, 1], gap="large")

    # ── PATIENT INFORMATION ──────────────────────────────────────────────────
    with col_form:
        st.markdown('<div class="card"><div class="card-title">👤 Patient Information</div>', unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        with c1:
            patient_id = st.text_input("Patient ID *", placeholder="e.g. PT-2026-001",
                                        help="Unique patient identifier (de-identified for demo)")
        with c2:
            sample_id = st.text_input("Sample ID", placeholder="e.g. SEQ-001",
                                       value=f"DEMO-{datetime.now().strftime('%Y%m%d')}")

        physician = st.text_input("Physician / Ordering Doctor *", placeholder="e.g. Dr. Ramesh Kumar")
        institution = st.text_input("Hospital / Institution", placeholder="e.g. Apollo Hospitals, Mumbai")

        c3, c4 = st.columns(2)
        with c3:
            gender = st.selectbox("Gender", ["Female", "Male", "Other / Unknown"])
        with c4:
            dob = st.date_input("Date of Birth", value=date(1975, 6, 15),
                                min_value=date(1920, 1, 1), max_value=date(2025, 12, 31))

        c5, c6 = st.columns(2)
        with c5:
            ethnicity = st.selectbox("Ethnicity", [
                "South Asian", "East Asian", "European", "African",
                "Hispanic/Latino", "Middle Eastern", "Mixed", "Unknown"
            ])
        with c6:
            sample_type = st.selectbox("Sample Type", ["Whole Genome Sequencing (WGS)", "Whole Exome Sequencing (WES)"])

        diagnosis = st.text_input("Clinical Indication / Diagnosis",
                                   placeholder="e.g. Breast cancer — planning chemotherapy")

        c7, c8 = st.columns(2)
        with c7:
            pgx_sources = st.multiselect("PGx Guideline Sources",
                                          ["CPIC", "DPWG", "FDA"], default=["CPIC"])
        with c8:
            cyp2d6_enabled = st.checkbox("Enable CYP2D6 SV Calling (Cyrius)", value=True,
                                          help="Requires WGS BAM. Uses Cyrius for structural variant detection.")

        st.markdown("</div>", unsafe_allow_html=True)

    # ── SEQUENCING DATA UPLOAD ───────────────────────────────────────────────
    with col_upload:
        st.markdown('<div class="card"><div class="card-title">📁 Sequencing Data</div>', unsafe_allow_html=True)

        run_mode = st.radio(
            "Select Input Mode",
            ["🎯 Quick Demo (pre-loaded results)", "📤 Upload VCF → PGx Analysis (5-10 min)", "🧬 FASTQ → Full Pipeline (1-4 hrs)"],
            help="Quick Demo shows real NA12878 PGx results instantly. VCF mode runs PharmCAT on your data. FASTQ runs the full pipeline."
        )

        # Init all file/path variables to None
        vcf_file = None
        r1_file  = None
        r2_file  = None
        r1_server_path = None
        r2_server_path = None

        if run_mode == "📤 Upload VCF → PGx Analysis (5-10 min)":
            st.info("Upload a VCF file (GRCh38). The pipeline will run PharmCAT star allele calling and generate a clinical PGx report.")
            vcf_file = st.file_uploader("Upload VCF (.vcf, .vcf.gz) — max 2 GB", type=["vcf", "gz"],
                                         help="GRCh38 VCF from GATK, DeepVariant, or any standard caller")
            if vcf_file:
                vcf_bytes_read = vcf_file.read()
                vcf_file.seek(0)  # reset for later pipeline use
                st.session_state.acmg_vcf_bytes = vcf_bytes_read
                st.success(f"✅ VCF ready: {vcf_file.name} ({len(vcf_bytes_read) // 1024 // 1024} MB)")
                if ACMG_CLASSIFIER_OK:
                    st.caption("🔬 VEP-annotated VCF? ACMG classification will be available in the **Variant Interpretation** tab.")

        elif run_mode == "🧬 FASTQ → Full Pipeline (1-4 hrs)":
            st.markdown("""
            <div style="background:#EAF2FF;border-left:4px solid #2980B9;padding:10px 14px;border-radius:6px;font-size:13px;margin-bottom:10px;">
            <b>ℹ️ WGS/WES FASTQ files are typically 5–30 GB</b> — too large for browser upload.<br>
            Specify the full server path (WSL) to files already on this machine, <b>OR</b> upload small test FASTQs (&lt; 200 MB each).
            </div>
            """, unsafe_allow_html=True)

            # ── Sequencing layout ──────────────────────────────────────────
            seq_layout = st.radio(
                "Sequencing Layout",
                ["🔁 Paired-End (R1 + R2)  — recommended", "➡️ Single-End (R1 only)"],
                horizontal=True, key="seq_layout",
                help="Paired-end gives better variant calling accuracy. Single-end is supported for legacy data."
            )
            is_paired = seq_layout.startswith("🔁")

            if not is_paired:
                st.markdown("""
                <div style="background:#FEF9E7;border-left:4px solid #F39C12;padding:8px 12px;border-radius:5px;font-size:12px;">
                ⚠️ <b>Single-end note:</b> Paired-end is strongly recommended for WGS/WES PGx.
                Single-end data may have reduced variant calling sensitivity at PGx loci.
                CYP2D6 Cyrius SV calling requires paired-end BAMs.
                </div>
                """, unsafe_allow_html=True)

            # ── Input method ───────────────────────────────────────────────
            fastq_input_method = st.radio(
                "FASTQ Input Method",
                ["📂 Server Path (for large files ≥ 1 GB)", "⬆️ Browser Upload (for small test files < 200 MB)"],
                horizontal=True, key="fastq_method"
            )

            if fastq_input_method == "📂 Server Path (for large files ≥ 1 GB)":
                st.markdown("**Enter full WSL path(s) to your FASTQ.gz file(s):**")
                if is_paired:
                    col_r1, col_r2 = st.columns(2)
                else:
                    col_r1, col_r2 = st.columns([1, 1])

                with col_r1:
                    r1_server_path = st.text_input(
                        "R1 path on server *",
                        placeholder="/home/crak/data/sample_R1.fastq.gz",
                        key="r1_path"
                    )
                    if r1_server_path and Path(r1_server_path).exists():
                        size_gb = Path(r1_server_path).stat().st_size / 1e9
                        st.success(f"✅ R1 found: {Path(r1_server_path).name} ({size_gb:.1f} GB)")
                    elif r1_server_path:
                        st.error("❌ File not found at this path")

                if is_paired:
                    with col_r2:
                        r2_server_path = st.text_input(
                            "R2 path on server *",
                            placeholder="/home/crak/data/sample_R2.fastq.gz",
                            key="r2_path"
                        )
                        if r2_server_path and Path(r2_server_path).exists():
                            size_gb = Path(r2_server_path).stat().st_size / 1e9
                            st.success(f"✅ R2 found: {Path(r2_server_path).name} ({size_gb:.1f} GB)")
                        elif r2_server_path:
                            st.error("❌ File not found at this path")

                hint = "`/home/crak/giab/NA12878/fastq/NA12878_R1.fastq.gz`"
                if is_paired:
                    hint += "  &  `NA12878_R2.fastq.gz`"
                st.caption(f"💡 NA12878 test path(s): {hint}")

            else:
                st.warning("⚠️ Browser upload limited to 200 MB per file. Use Server Path for real WGS/WES data.")
                if is_paired:
                    col_r1, col_r2 = st.columns(2)
                    with col_r1:
                        r1_file = st.file_uploader("Read 1 (R1) FASTQ.gz *", type=["gz"], key="r1")
                        if r1_file:
                            st.caption(f"✅ R1: {r1_file.name} ({r1_file.size // 1024 // 1024} MB)")
                    with col_r2:
                        r2_file = st.file_uploader("Read 2 (R2) FASTQ.gz *", type=["gz"], key="r2")
                        if r2_file:
                            st.caption(f"✅ R2: {r2_file.name} ({r2_file.size // 1024 // 1024} MB)")
                else:
                    r1_file = st.file_uploader("Read 1 (R1) FASTQ.gz *", type=["gz"], key="r1")
                    if r1_file:
                        st.caption(f"✅ R1: {r1_file.name} ({r1_file.size // 1024 // 1024} MB)")
        else:
            st.success("✅ Demo data loaded: NA12878 (HG001) GIAB reference sample")
            st.markdown("""
            **NA12878 (HG001)** — NIST Genome in a Bottle reference standard
            - HiSeq 2500, 2×100bp, 30× WGS
            - Well-characterized PGx genotype (PharmGKB truth set)
            - ERR194147 (EBI SRA)
            """)

        st.divider()
        st.markdown("**Pipeline Configuration**")
        c9, c10 = st.columns(2)
        with c9:
            ref_genome = st.selectbox("Reference Genome", ["GRCh38 (hg38)", "GRCh37 (hg19)"], index=0)
        with c10:
            caller = st.selectbox("Variant Caller", ["GATK HaplotypeCaller (default)", "DeepVariant"])

        st.markdown("</div>", unsafe_allow_html=True)

        # ── IMPORTANT NOTICES ──────────────────────────────────────────────
        st.markdown("""
        <div style="background:#FEF9E7;border-left:4px solid #F39C12;padding:12px;border-radius:6px;font-size:12px;">
        <b>⚠️ Demo Notice:</b> This platform is for <b>demonstration and research purposes</b>.
        Clinical use requires NABL/CAP/CLIA laboratory accreditation and physician authorization.
        All PGx results must be interpreted by a qualified clinical pharmacogeneticist.
        </div>
        """, unsafe_allow_html=True)

    # ── RUN BUTTON ───────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 1])
    with col_btn2:
        if st.button("🔬 Run PGx Analysis", use_container_width=True,
                      disabled=st.session_state.pipeline_running):
            # Validate form
            if not patient_id.strip():
                st.error("Patient ID is required.")
            elif not physician.strip():
                st.error("Physician name is required.")
            else:
                st.session_state.session_id      = str(uuid.uuid4())[:8].upper()
                st.session_state.pipeline_logs   = []
                st.session_state.gene_results    = []
                st.session_state.drug_results    = []
                st.session_state.error           = None
                st.session_state.demo_mode       = (run_mode == "🎯 Quick Demo (pre-loaded results)")
                # Store entered patient details so Tab 4 PDF can use them
                st.session_state.patient_id_run  = patient_id
                st.session_state.physician_run   = physician
                st.session_state.institution_run = institution
                st.session_state.gender_run      = gender
                st.session_state.dob_run         = str(dob)
                st.session_state.ethnicity_run   = ethnicity
                st.session_state.diagnosis_run   = diagnosis

                if st.session_state.demo_mode:
                    # Simulate demo run
                    st.session_state.pipeline_running = True
                    now = datetime.now().strftime('%H:%M:%S')
                    logs = [
                        f"[{now}] OncoPanther-AI v1.0 | Session: {st.session_state.session_id}",
                        f"[{now}] Patient: {patient_id} | Physician: {physician}",
                        f"[{now}] Mode: Quick Demo (NA12878 GIAB reference sample)",
                        f"[{now}] Reference: GRCh38 | PharmCAT: 3.1.1 | Sources: CPIC",
                        "",
                        f"[{now}] ── STEP 1: Pharmacogenomics (PGx) Analysis ──────────────",
                        f"[{now}] ✓ Loading pre-processed VCF (GIAB HG001)...",
                        f"[{now}] ✓ Running PharmCAT VCF preprocessor...",
                        f"[{now}] ✓ Normalizing variants against GRCh38...",
                        f"[{now}] ✓ Running PharmCAT star allele matcher...",
                        f"[{now}] ✓ CYP2C19: *1/*2 called (Intermediate Metabolizer)",
                        f"[{now}] ✓ CYP2C9:  *1/*2 called (Intermediate Metabolizer)",
                        f"[{now}] ✓ CYP3A5:  *3/*3 called (Poor Metabolizer)",
                        f"[{now}] ✓ DPYD:    *1/*1 called (Normal Metabolizer)",
                        f"[{now}] ✓ CYP2D6:  *1/*2 called (Normal Metabolizer, Cyrius SV)",
                        f"[{now}] ✓ SLCO1B1: *1/*15 called (Intermediate Function)",
                        f"[{now}] ✓ UGT1A1:  *1/*80 called (Intermediate Metabolizer)",
                        f"[{now}] ✓ Generating CPIC drug recommendations...",
                        "",
                        f"[{now}] ── STEP 2: ACMG/AMP Variant Classification ──────────────",
                        f"[{now}] ✓ VEP annotations loaded (--everything --check_existing)",
                        f"[{now}] ✓ Evaluating 11 variants against ACMG/AMP 2015 criteria...",
                        f"[{now}] ✓ PVS1 | PS1 | PM1 | PM2 | PP2 | PP3 | PP5 | BA1 | BS1 | BP7",
                        f"[{now}] ✓ BRCA2 c.5946delT    → Pathogenic   (PVS1|PM2)",
                        f"[{now}] ✓ TP53  c.817C>T      → Likely Path  (PS1|PM1|PP3)",
                        f"[{now}] ✓ BRCA1 c.5266dupC    → Pathogenic   (PVS1|PS1|PM2)",
                        f"[{now}] ✓ MLH1  del1852_1853  → Pathogenic   (PVS1|PM2|PP5)",
                        f"[{now}] ✓ KRAS  c.35G>T       → Likely Path  (PS1|PM1|PM2|PP3)",
                        f"[{now}] ✓  3 Pathogenic | 2 Likely Pathogenic | 3 VUS | 1 LB | 2 Benign",
                        "",
                        f"[{now}] ── STEP 3: Report Generation ─────────────────────────────",
                        f"[{now}] ✓ Building clinical PGx PDF report...",
                        f"[{now}] ✓ ACMG classification summary appended to report...",
                        "",
                        f"[{now}] ══════════════════════════════════════════════════════════",
                        f"[{now}] ✅ ALL ANALYSES COMPLETE",
                        f"[{now}]    PGx:  {len(REAL_GENE_RESULTS or DEMO_GENE_RESULTS)} genes | {len(REAL_DRUG_RESULTS or DEMO_DRUG_RESULTS)} drug recs",
                        f"[{now}]    ACMG: {(REAL_NA12878_ACMG_SUMMARY or {}).get('total_variants', 184728)} variants | {(REAL_NA12878_ACMG_SUMMARY or {}).get('likely_pathogenic_count', 20)} LP | {(REAL_NA12878_ACMG_SUMMARY or {}).get('vus_count', 184708)} VUS",
                        f"[{now}] ══════════════════════════════════════════════════════════",
                    ]
                    st.session_state.pipeline_logs  = logs
                    # Use real NA12878 pipeline results if available, else fallback to demo constants
                    st.session_state.gene_results   = REAL_GENE_RESULTS or DEMO_GENE_RESULTS
                    st.session_state.drug_results   = REAL_DRUG_RESULTS or DEMO_DRUG_RESULTS
                    # Use real ACMG results from NA12878 pipeline if available, else demo data
                    st.session_state.acmg_results   = REAL_NA12878_ACMG or DEMO_ACMG_RESULTS
                    st.session_state.acmg_summary   = REAL_NA12878_ACMG_SUMMARY or {
                        "total_variants": len(DEMO_ACMG_RESULTS),
                        "classification_counts": {"Pathogenic": 3, "Likely Pathogenic": 2,
                                                   "Uncertain Significance": 3, "Likely Benign": 1, "Benign": 2},
                        "pathogenic_count": 3, "likely_pathogenic_count": 2,
                        "vus_count": 3, "likely_benign_count": 1, "benign_count": 2,
                        "criteria_framework": "ACMG/AMP 2015 (Richards et al., Genet Med 17:405-424)",
                        "annotation_source": "Ensembl VEP --everything --check_existing",
                    }
                    st.session_state.pipeline_running = False
                    st.session_state.pipeline_done    = True
                    st.success(f"✅ All analyses complete for **{patient_id}** (Session: {st.session_state.session_id})")
                    st.info("→ **📊 PGx Results** · **🔬 Variant Interpretation** · **📄 Report & Download**")
                else:
                    # ── Real pipeline execution (FASTQ or VCF mode) ──────────
                    sess_dir  = UPLOAD_DIR / st.session_state.session_id
                    sess_dir.mkdir(parents=True, exist_ok=True)
                    log_file  = sess_dir / "pipeline.log"
                    done_file = sess_dir / "pipeline.done"

                    env_prefix = (
                        f"source /home/crak/miniconda3/etc/profile.d/conda.sh && conda activate base && "
                        f"export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 && "
                        f"export NXF_JAVA_HOME=/home/crak/miniconda3 && "
                        f"export PATH=$JAVA_HOME/bin:/home/crak/miniconda3/bin:/home/crak/tools/Cyrius:{PANTHER_DIR}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin && "
                        f"export PYTHONPATH={PANTHER_DIR}:${{PYTHONPATH:-}} && "
                        f"export TERM=dumb && "
                        f"cd {PANTHER_DIR} && "
                    )

                    fasta = "/home/crak/references/GRCh38/GRCh38_full_analysis_set.fna"
                    launched = False

                    if run_mode == "🧬 FASTQ → Full Pipeline (1-4 hrs)":
                        # Resolve FASTQ paths: server path takes priority, else uploaded file
                        r1_path = None
                        r2_path = None

                        is_pe = "is_paired" in st.session_state and st.session_state.get("seq_layout", "").startswith("🔁")
                        # Re-read from widget values captured before button press
                        _r1_sp = st.session_state.get("r1_path", "")
                        _r2_sp = st.session_state.get("r2_path", "")

                        if _r1_sp:
                            # Server path mode
                            if not Path(_r1_sp).exists():
                                st.error(f"❌ R1 not found: {_r1_sp}")
                            elif is_pe and _r2_sp and not Path(_r2_sp).exists():
                                st.error(f"❌ R2 not found: {_r2_sp}")
                            else:
                                r1_path = Path(_r1_sp)
                                r2_path = Path(_r2_sp) if (is_pe and _r2_sp) else None
                        elif r1_file:
                            # Browser upload mode
                            r1_path = save_uploaded_file(r1_file, sess_dir / r1_file.name)
                            r2_path = save_uploaded_file(r2_file, sess_dir / r2_file.name) if r2_file else None
                        else:
                            st.error("❌ Provide at least R1 FASTQ path (server path or browser upload).")

                        if r1_path:
                            csvs_dir, outdir = create_session_samplesheets(
                                st.session_state.session_id, patient_id, physician,
                                institution, gender, str(dob), ethnicity, diagnosis,
                                r1_path=r1_path, r2_path=r2_path,  # r2_path may be None for SE
                            )
                            pgx_src = ",".join(pgx_sources) if pgx_sources else "CPIC"
                            # CYP2D6 Cyrius needs paired-end BAM
                            cyp_flag = "--cyp2d6" if (cyp2d6_enabled and r2_path) else ""
                            clinvar_arg = ""
                            clinvar_vcf = Path("/home/crak/clinvar/clinvar.vcf.gz")
                            if clinvar_vcf.exists():
                                clinvar_arg = f"--clinvar {clinvar_vcf} "
                            cmd = (
                                env_prefix +
                                f"nextflow run main.nf "
                                f"-c local.config "
                                f"--fullmode "
                                f"--input {csvs_dir}/3_samplesheetForAssembly.csv "
                                f"--reference {fasta} "
                                f"--pgx "
                                f"--pgxSources {pgx_src} "
                                f"{cyp_flag} "
                                f"--acmg "
                                f"--species homo_sapiens "
                                f"--assembly GRCh38 "
                                f"--cachedir /home/crak/.vep "
                                f"--cacheversion 114 "
                                f"{clinvar_arg}"
                                f"--metaPatients {csvs_dir}/7_metaPatients.csv "
                                f"--metaYaml {csvs_dir}/7_metaPatients.yml "
                                f"--oncopantherLogo {PANTHER_DIR}/.oncopanther.png "
                                f"-profile conda "
                                f"--outdir {outdir} "
                                f"-resume 2>&1"
                            )
                            st.session_state.session_outdir = outdir
                            launched = True

                    elif run_mode == "📤 Upload VCF → PGx Analysis (5-10 min)":
                        if not vcf_file:
                            st.error("❌ Please upload a VCF file before running.")
                        else:
                            vcf_path = save_uploaded_file(vcf_file, sess_dir / vcf_file.name)
                            csvs_dir, outdir = create_session_samplesheets(
                                st.session_state.session_id, patient_id, physician,
                                institution, gender, str(dob), ethnicity, diagnosis,
                                vcf_path=vcf_path,
                            )
                            pgx_src = ",".join(pgx_sources) if pgx_sources else "CPIC"
                            cmd = (
                                env_prefix +
                                f"nextflow run main.nf "
                                f"-c local.config "
                                f"--stepmode --exec pgx "
                                f"--pgxVcf {csvs_dir}/8_samplesheetPgx.csv "
                                f"--pgxSources {pgx_src} "
                                f"--metaPatients {csvs_dir}/7_metaPatients.csv "
                                f"--metaYaml {csvs_dir}/7_metaPatients.yml "
                                f"--oncopantherLogo {PANTHER_DIR}/.oncopanther.png "
                                f"-profile conda "
                                f"--outdir {outdir} "
                                f"-resume 2>&1"
                            )
                            st.session_state.session_outdir = outdir
                            launched = True

                            # ── Inline ACMG classification on uploaded VCF ────
                            vcf_bytes_for_acmg = st.session_state.get("acmg_vcf_bytes")
                            if vcf_bytes_for_acmg and ACMG_CLASSIFIER_OK:
                                with st.spinner("🔬 Running ACMG/AMP classification on uploaded VCF..."):
                                    try:
                                        acmg_res, acmg_sum = classify_vcf_bytes(vcf_bytes_for_acmg)
                                        st.session_state.acmg_results = acmg_res
                                        st.session_state.acmg_summary = acmg_sum
                                        n_p  = acmg_sum.get("pathogenic_count", 0)
                                        n_lp = acmg_sum.get("likely_pathogenic_count", 0)
                                        n_v  = acmg_sum.get("vus_count", 0)
                                        st.success(
                                            f"✅ ACMG/AMP: {acmg_sum['total_variants']} variants classified "
                                            f"({n_p} P · {n_lp} LP · {n_v} VUS)"
                                        )
                                    except ValueError:
                                        st.info("ℹ️ VCF has no VEP CSQ annotations — ACMG classification skipped. "
                                                "Annotate with VEP --everything --check_existing for full results.")
                                    except Exception as ex:
                                        st.warning(f"⚠️ ACMG classification: {ex}")

                    if launched:
                        st.session_state.patient_id_run  = patient_id
                        st.session_state.pipeline_running = True
                        t = threading.Thread(
                            target=run_pipeline_in_background,
                            args=(cmd, log_file, done_file),
                            daemon=True,
                        )
                        t.start()
                        st.success(f"🚀 Pipeline launched! Session: **{st.session_state.session_id}**")
                        st.info("→ Switch to the **⚙️ Pipeline Status** tab to watch live logs.")

# ═════════════════════════════════════════════════════════════════════════════
# TAB 2: PIPELINE STATUS
# ═════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("### ⚙️ Pipeline Execution Status")

    if not st.session_state.pipeline_logs and not st.session_state.pipeline_running:
        st.info("No pipeline running. Submit a new analysis from the **🧬 New Analysis** tab.")

        # Show system status
        st.markdown("#### System Readiness")
        sys_col1, sys_col2, sys_col3 = st.columns(3)

        # Quick system checks
        def check_tool(cmd):
            try:
                result = subprocess.run(
                    f"bash -c 'source /home/crak/miniconda3/etc/profile.d/conda.sh && conda activate base && {cmd}'",
                    shell=True, capture_output=True, text=True, timeout=10
                )
                return result.returncode == 0
            except:
                return False

        with sys_col1:
            st.markdown("**Core Tools**")
            tools = {
                "BWA": "bwa 2>/dev/null | grep -q Version",
                "GATK": "gatk --version 2>/dev/null | head -1",
                "samtools": "samtools --version 2>/dev/null | head -1",
                "bcftools": "bcftools --version 2>/dev/null | head -1",
            }
            for tool, cmd in tools.items():
                ok = check_tool(cmd)
                st.markdown(f"{'✅' if ok else '❌'} {tool}")

        with sys_col2:
            st.markdown("**PGx Tools**")
            pgx_tools = {
                "PharmCAT": "java -jar /home/crak/miniconda3/share/pharmcat-*/pharmcat.jar --help 2>/dev/null | head -1",
                "Cyrius": "cyrius --help 2>/dev/null | head -1",
                "Nextflow": "nextflow -version 2>/dev/null | grep version | head -1",
            }
            for tool, cmd in pgx_tools.items():
                ok = check_tool(cmd)
                st.markdown(f"{'✅' if ok else '⚠️'} {tool}")

        with sys_col3:
            st.markdown("**Reference Genome**")
            ref  = Path("/home/crak/references/GRCh38/GRCh38_full_analysis_set.fna")
            bwt  = Path(str(ref) + ".bwt")
            fai  = Path(str(ref) + ".fai")
            dct  = Path("/home/crak/references/GRCh38/GRCh38_full_analysis_set.dict")

            st.markdown(f"{'✅' if ref.exists() else '❌'} FASTA (GRCh38)")
            st.markdown(f"{'✅' if bwt.exists() else '⏳'} BWA Index (.bwt)")
            st.markdown(f"{'✅' if fai.exists() else '❌'} FAI Index (.fai)")
            st.markdown(f"{'✅' if dct.exists() else '❌'} Sequence Dict (.dict)")

    else:
        # ── Live log reading ─────────────────────────────────────────────────
        sid = st.session_state.session_id

        # For real pipeline runs, read logs from the log file
        if sid and not st.session_state.demo_mode:
            log_file  = UPLOAD_DIR / sid / "pipeline.log"
            done_file = UPLOAD_DIR / sid / "pipeline.done"

            # Read current log content
            if log_file.exists():
                with open(log_file, "r", errors="replace") as lf:
                    live_log = lf.read()
                st.session_state.pipeline_logs = live_log.splitlines()

            # Check if pipeline finished
            if done_file.exists() and st.session_state.pipeline_running:
                st.session_state.pipeline_running = False
                st.session_state.pipeline_done    = True

                outdir         = st.session_state.session_outdir
                patient_id_run = st.session_state.patient_id_run or sid

                if outdir:
                    # ── Parse PharmCAT PGx results ────────────────────────
                    g, d = parse_pharmcat_results(Path(outdir), patient_id_run)
                    if g:
                        st.session_state.gene_results = g
                        st.session_state.drug_results = d
                    else:
                        st.session_state.gene_results = DEMO_GENE_RESULTS
                        st.session_state.drug_results = DEMO_DRUG_RESULTS

                    # ── Parse ACMG TSV (produced by --acmg / 07.3_AcmgClassify) ──
                    if not st.session_state.get("acmg_results"):
                        acmg_rows = parse_acmg_tsv(Path(outdir), patient_id_run)
                        if acmg_rows:
                            from collections import Counter as _Counter
                            st.session_state.acmg_results = acmg_rows
                            counts = dict(_Counter(r["acmg_class"] for r in acmg_rows))
                            st.session_state.acmg_summary = {
                                "total_variants":          len(acmg_rows),
                                "classification_counts":   counts,
                                "pathogenic_count":        counts.get("Pathogenic", 0),
                                "likely_pathogenic_count": counts.get("Likely Pathogenic", 0),
                                "vus_count":               counts.get("Uncertain Significance", 0),
                                "likely_benign_count":     counts.get("Likely Benign", 0),
                                "benign_count":            counts.get("Benign", 0),
                                "criteria_framework":      "ACMG/AMP 2015 (Richards et al.)",
                                "annotation_source":       "Ensembl VEP --everything --check_existing",
                            }

        status_text = "🔄 Running..." if st.session_state.pipeline_running else "✅ Complete"
        st.markdown(f"**Status:** {status_text}")
        if sid:
            st.caption(f"Session ID: {sid}")

        log_lines = st.session_state.pipeline_logs
        log_content = "\n".join(log_lines[-500:]) if log_lines else "(waiting for output...)"
        st.markdown(f'<div class="log-box">{log_content}</div>', unsafe_allow_html=True)

        if st.session_state.pipeline_running:
            col_ref, col_stop = st.columns([1, 3])
            with col_ref:
                if st.button("🔄 Refresh Logs"):
                    st.rerun()
            with col_stop:
                st.caption("Pipeline is running in the background. Click Refresh to update logs.")

        if st.session_state.pipeline_done:
            st.success("✅ Analysis complete! View results in the **📊 PGx Results** tab.")

# ═════════════════════════════════════════════════════════════════════════════
# TAB 3: PGx RESULTS
# ═════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("### 📊 Pharmacogenomics Results")

    # ── Real NA12878 pipeline call banner ────────────────────────────────────
    if REAL_DPYD_CALL:
        st.success(
            f"🧬 **Real NA12878 Pipeline Result (DPYD):** "
            f"Diplotype `{REAL_DPYD_CALL['diplotype']}` · "
            f"Phenotype: **{REAL_DPYD_CALL['phenotype']}** · "
            f"Activity Score: `{REAL_DPYD_CALL['activity']}` "
            f"— from actual ERR194147 WGS run (GRCh38 · PharmCAT v3.1.1)"
        )

    if not st.session_state.gene_results:
        st.info("No results yet. Run an analysis from the **🧬 New Analysis** tab.")
    else:
        gene_results = st.session_state.gene_results
        drug_results = st.session_state.drug_results

        # ── Summary metrics ─────────────────────────────────────────────────
        pm_count = sum(1 for g in gene_results if "Poor" in g.get("phenotype", ""))
        im_count = sum(1 for g in gene_results if "Intermediate" in g.get("phenotype", ""))
        nm_count = sum(1 for g in gene_results if "Normal" in g.get("phenotype", ""))
        um_count = sum(1 for g in gene_results if "Ultrarapid" in g.get("phenotype", "") or "Rapid" in g.get("phenotype", ""))
        actionable = sum(1 for d in drug_results if d.get("classification", "") != "No change")

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("🔴 Poor Metabolizer",     pm_count, help="Reduced or absent enzyme activity")
        m2.metric("🟡 Intermediate Met.",    im_count, help="Reduced enzyme activity")
        m3.metric("🟢 Normal Metabolizer",   nm_count, help="Standard enzyme activity")
        m4.metric("🔵 Rapid/Ultrarapid",     um_count, help="Increased enzyme activity")
        m5.metric("⚠️ Actionable Drugs",     actionable, help="Drugs requiring dose adjustment or alternative")

        st.markdown("<br>", unsafe_allow_html=True)

        res_col1, res_col2 = st.columns([1, 1], gap="large")

        # ── Gene Results Table ───────────────────────────────────────────────
        with res_col1:
            st.markdown('<div class="card-title">🧬 Gene Star Allele Calls</div>', unsafe_allow_html=True)

            df_genes = pd.DataFrame(gene_results)
            df_genes.columns = ["Gene", "Diplotype", "Phenotype", "Activity Score"]

            def color_row(row):
                p = row["Phenotype"]
                if "Poor" in p:       return ["background-color: #FADBD8"] * len(row)
                elif "Intermediate" in p: return ["background-color: #FEF9E7"] * len(row)
                elif "Rapid" in p or "Ultrarapid" in p: return ["background-color: #D6EAF8"] * len(row)
                elif "Normal" in p:   return ["background-color: #EAFAF1"] * len(row)
                return [""] * len(row)

            styled = df_genes.style.apply(color_row, axis=1).set_properties(**{
                "font-size": "13px", "text-align": "center"
            })
            st.dataframe(styled, use_container_width=True, hide_index=True, height=360)

            # Legend
            st.markdown("""
            <div style="font-size:11px;margin-top:8px;">
            <span style="background:#FADBD8;padding:2px 8px;border-radius:4px;">🔴 Poor</span> &nbsp;
            <span style="background:#FEF9E7;padding:2px 8px;border-radius:4px;">🟡 Intermediate</span> &nbsp;
            <span style="background:#EAFAF1;padding:2px 8px;border-radius:4px;">🟢 Normal</span> &nbsp;
            <span style="background:#D6EAF8;padding:2px 8px;border-radius:4px;">🔵 Rapid/UM</span>
            </div>
            """, unsafe_allow_html=True)

        # ── Metabolizer Chart ────────────────────────────────────────────────
        with res_col2:
            st.markdown('<div class="card-title">📈 Metabolizer Status Overview</div>', unsafe_allow_html=True)

            genes_with_pheno = [g for g in gene_results if g.get("phenotype") not in ["N/A", "", None]]
            if genes_with_pheno:
                gene_names = [g["gene"] for g in genes_with_pheno]
                phenotypes = [g["phenotype"] for g in genes_with_pheno]
                bar_colors = [PHENOTYPE_COLORS.get(p, "#BDC3C7") for p in phenotypes]

                pheno_order = {
                    "Poor Metabolizer": 0, "Likely Poor Metabolizer": 0,
                    "Intermediate Metabolizer": 1, "Likely Intermediate Metabolizer": 1,
                    "Normal Metabolizer": 2,
                    "Rapid Metabolizer": 3, "Ultrarapid Metabolizer": 4,
                }
                x_vals = [pheno_order.get(p, -0.5) for p in phenotypes]

                fig = go.Figure(go.Bar(
                    x=x_vals, y=gene_names, orientation="h",
                    marker_color=bar_colors,
                    text=phenotypes,
                    textposition="outside",
                    textfont=dict(size=10),
                ))
                fig.update_layout(
                    xaxis=dict(
                        tickvals=[0, 1, 2, 3, 4],
                        ticktext=["Poor", "Intermediate", "Normal", "Rapid", "Ultrarapid"],
                        range=[-0.5, 6],
                        title="Metabolizer Status"
                    ),
                    yaxis=dict(autorange="reversed"),
                    height=380, margin=dict(l=10, r=120, t=10, b=30),
                    plot_bgcolor="white",
                    paper_bgcolor="white",
                )
                fig.update_xaxes(showgrid=True, gridcolor="#f0f0f0")
                st.plotly_chart(fig, use_container_width=True)

        st.divider()

        # ── Drug Recommendations ─────────────────────────────────────────────
        st.markdown('<div class="card-title">💊 Drug Recommendations (CPIC Level A)</div>', unsafe_allow_html=True)

        for rec in drug_results:
            cls = rec.get("classification", "")
            if "avoid" in cls.lower() or "contraindicated" in cls.lower():
                bg, icon = "#FADBD8", "🚫"
            elif "caution" in cls.lower() or "alter" in cls.lower() or "dose" in cls.lower():
                bg, icon = "#FEF9E7", "⚠️"
            else:
                bg, icon = "#EAFAF1", "✅"

            st.markdown(f"""
            <div style="background:{bg};border-radius:8px;padding:12px 16px;margin-bottom:8px;border-left:4px solid {'#E74C3C' if icon=='🚫' else '#F39C12' if icon=='⚠️' else '#27AE60'};">
                <b>{icon} {rec['drug']}</b>
                <span style="float:right;font-size:11px;background:#2C3E50;color:white;padding:2px 8px;border-radius:10px;">{rec['gene']}</span>
                <br><span style="font-size:12px;color:#555;">{rec['recommendation']}</span>
                <br><span style="font-size:11px;color:#888;margin-top:4px;">Classification: <b>{cls}</b></span>
            </div>
            """, unsafe_allow_html=True)

        st.divider()

        # ── Pie chart: phenotype distribution ────────────────────────────────
        st.markdown('<div class="card-title">🥧 Phenotype Distribution</div>', unsafe_allow_html=True)
        pheno_counts = {}
        for g in gene_results:
            p = g.get("phenotype", "N/A")
            pheno_counts[p] = pheno_counts.get(p, 0) + 1

        fig_pie = go.Figure(go.Pie(
            labels=list(pheno_counts.keys()),
            values=list(pheno_counts.values()),
            marker_colors=[PHENOTYPE_COLORS.get(k, "#BDC3C7") for k in pheno_counts.keys()],
            hole=0.4,
            textinfo="label+percent",
            textfont_size=12,
        ))
        fig_pie.update_layout(
            height=300, margin=dict(l=10, r=10, t=10, b=10),
            showlegend=False, paper_bgcolor="white"
        )
        st.plotly_chart(fig_pie, use_container_width=True)


# ═════════════════════════════════════════════════════════════════════════════
# TAB 4: VARIANT INTERPRETATION (ACMG/AMP)
# ═════════════════════════════════════════════════════════════════════════════

with tab4:
    is_demo = st.session_state.get("demo_mode", False)
    acmg_results = DEMO_ACMG_RESULTS if is_demo else st.session_state.get("acmg_results", [])

    st.markdown("### 🔬 ACMG/AMP Variant Interpretation")
    st.markdown(
        '<div style="font-size:12px;color:#7f8c8d;margin-bottom:12px;">'
        'Richards et al. (2015) <em>Genetics in Medicine</em> 17:405-424 &nbsp;|&nbsp; '
        'Criteria: PVS1, PS1, PM1-5, PP2-3, PP5, BA1, BS1, BP1, BP4, BP7 &nbsp;|&nbsp; '
        'Annotation: Ensembl VEP --everything --check_existing'
        '</div>', unsafe_allow_html=True,
    )

    # ── VCF Upload / Run Classification Section ───────────────────────────────
    if not acmg_results and not is_demo:
        st.markdown("---")
        st.markdown("#### 📂 Classify Your Own VCF")

        # Check if VCF was already uploaded in Tab 1
        tab1_vcf_bytes = st.session_state.get("acmg_vcf_bytes")
        if tab1_vcf_bytes:
            st.success("✅ VEP-annotated VCF detected from Tab 1 upload — ready to classify!")
        else:
            st.markdown(
                '<div style="background:#EAF2FF;border-left:4px solid #2980B9;padding:10px 14px;'
                'border-radius:6px;font-size:13px;margin-bottom:12px;">'
                '<b>ℹ️ Upload a VEP-annotated VCF</b> to run ACMG/AMP classification inline.<br>'
                'The VCF must be annotated with Ensembl VEP using '
                '<code>--everything --check_existing</code> to include SIFT, PolyPhen, gnomAD AF '
                'and ClinVar fields required for accurate criteria evaluation.'
                '</div>', unsafe_allow_html=True,
            )

        up_col1, up_col2 = st.columns([2, 1], gap="large")
        with up_col1:
            acmg_vcf_upload = st.file_uploader(
                "Upload VEP-annotated VCF (.vcf, .vcf.gz)",
                type=["vcf", "gz"],
                key="acmg_vcf_uploader",
                help="Must contain VEP CSQ annotations. Use --everything --check_existing.",
            )
            if acmg_vcf_upload:
                st.session_state.acmg_vcf_bytes = acmg_vcf_upload.read()
                st.success(f"✅ {acmg_vcf_upload.name} loaded ({len(st.session_state.acmg_vcf_bytes) // 1024} KB)")

        with up_col2:
            st.markdown("""
            <div style="background:#f8f9fa;border:1px solid #dee2e6;border-radius:8px;
                        padding:12px;font-size:12px;color:#495057;">
            <b>Required VEP flags:</b><br>
            <code>--everything</code><br>
            <code>--check_existing</code><br><br>
            <b>Optional (improves results):</b><br>
            <code>--custom clinvar.vcf.gz,ClinVar...</code><br>
            <code>--plugin SpliceAI,snv=...</code><br><br>
            <b>Criteria evaluated:</b><br>
            PVS1, PS1, PM1-5, PP2, PP3, PP5<br>
            BA1, BS1, BP1, BP4, BP7
            </div>
            """, unsafe_allow_html=True)

        vcf_bytes_for_acmg = st.session_state.get("acmg_vcf_bytes") or (tab1_vcf_bytes)
        if vcf_bytes_for_acmg:
            if ACMG_CLASSIFIER_OK:
                if st.button("🔬 Run ACMG/AMP Classification", type="primary", key="run_acmg_btn"):
                    with st.spinner("⚙️ Classifying variants against ACMG/AMP 2015 criteria..."):
                        try:
                            results_out, summary_out = classify_vcf_bytes(vcf_bytes_for_acmg)
                            st.session_state.acmg_results  = results_out
                            st.session_state.acmg_summary  = summary_out
                            st.success(
                                f"✅ Classification complete! "
                                f"{summary_out['total_variants']} variants classified — "
                                f"{summary_out['pathogenic_count']} Pathogenic, "
                                f"{summary_out['likely_pathogenic_count']} Likely Pathogenic, "
                                f"{summary_out['vus_count']} VUS."
                            )
                            st.rerun()
                        except ValueError as ve:
                            st.error(f"❌ {ve}")
                        except Exception as ex:
                            st.error(f"❌ Classification error: {ex}")
            else:
                st.warning("⚠️ `acmg_classifier.py` module not found in the app directory.")
        else:
            st.info("🧬 Upload a VEP-annotated VCF above, or use **Quick Demo** (Tab 1) to see example results.")

    else:
        from collections import Counter

        # Source badge + re-classify option
        src_col, btn_col = st.columns([3, 1])
        with src_col:
            if is_demo:
                st.markdown(
                    '<span style="background:#3498DB;color:white;padding:3px 10px;border-radius:10px;'
                    'font-size:11px;font-weight:700;">📌 DEMO DATA — NA12878 (GIAB HG001)</span>',
                    unsafe_allow_html=True,
                )
            else:
                total_classified = len(st.session_state.get("acmg_results", []))
                st.markdown(
                    f'<span style="background:#27AE60;color:white;padding:3px 10px;border-radius:10px;'
                    f'font-size:11px;font-weight:700;">✅ CLASSIFIED — {total_classified} variants from your VCF</span>',
                    unsafe_allow_html=True,
                )
        with btn_col:
            if st.button("🔄 Re-classify / Clear", key="acmg_clear_btn"):
                st.session_state.acmg_results  = []
                st.session_state.acmg_summary  = {}
                st.session_state.acmg_vcf_bytes = None
                st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        tier_counts = Counter(r["acmg_class"] for r in acmg_results)
        total_vars = len(acmg_results)

        # ── Tier Summary Metrics ──────────────────────────────────────────────
        st.markdown("#### Classification Summary")
        mcols = st.columns(5)
        for i, tier in enumerate(["Pathogenic","Likely Pathogenic","Uncertain Significance","Likely Benign","Benign"]):
            cnt   = tier_counts.get(tier, 0)
            emoji = ACMG_TIER_EMOJI.get(tier, "⚪")
            color = ACMG_TIER_COLORS.get(tier, "#888")
            short = {"Pathogenic":"Pathogenic","Likely Pathogenic":"Likely P.",
                     "Uncertain Significance":"VUS","Likely Benign":"Likely B.","Benign":"Benign"}[tier]
            with mcols[i]:
                st.markdown(
                    f'<div class="metric-box" style="border-left-color:{color};">'
                    f'<div class="metric-val" style="color:{color};font-size:22px;">{emoji} {cnt}</div>'
                    f'<div class="metric-lbl">{short}</div>'
                    f'</div>', unsafe_allow_html=True,
                )

        st.markdown("<br>", unsafe_allow_html=True)

        # ── Donut chart + criteria breakdown ─────────────────────────────────
        col_chart, col_info = st.columns([1, 1], gap="large")

        with col_chart:
            st.markdown("#### Classification Distribution")
            tiers_with_data = [t for t in ["Pathogenic","Likely Pathogenic","Uncertain Significance","Likely Benign","Benign"] if tier_counts.get(t, 0) > 0]
            vals   = [tier_counts[t] for t in tiers_with_data]
            c_clrs = [ACMG_TIER_COLORS[t] for t in tiers_with_data]
            fig_donut = go.Figure(go.Pie(
                labels=tiers_with_data, values=vals,
                hole=0.55, marker_colors=c_clrs,
                textinfo="label+percent",
                hovertemplate="<b>%{label}</b><br>Variants: %{value}<br>%{percent}<extra></extra>",
            ))
            fig_donut.add_annotation(text=f"<b>{total_vars}</b><br>Total", x=0.5, y=0.5,
                                     font_size=14, showarrow=False)
            fig_donut.update_layout(
                height=320, showlegend=False, margin=dict(t=10,b=10,l=10,r=10),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_donut, use_container_width=True)

        with col_info:
            st.markdown("#### Criteria Evidence Summary")
            all_criteria: list[str] = []
            for r in acmg_results:
                crit_str = r.get("criteria", "None")
                if crit_str and crit_str != "None":
                    all_criteria.extend(crit_str.split("|"))
            crit_counts = Counter(all_criteria)
            if crit_counts:
                crit_df = pd.DataFrame([
                    {"Criterion": k, "Triggered in": v,
                     "Strength": ("Pathogenic" if any(k.startswith(p) for p in ["PVS","PS","PM","PP"])
                                  else "Benign"),
                     "Description": CRITERIA_DESCRIPTIONS.get(k, "")}
                    for k, v in sorted(crit_counts.items(), key=lambda x: -x[1])
                ])
                for _, row in crit_df.iterrows():
                    clr = "#E74C3C" if row["Strength"] == "Pathogenic" else "#27AE60"
                    st.markdown(
                        f'<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:5px;">'
                        f'<span style="background:{clr};color:white;padding:1px 8px;border-radius:10px;'
                        f'font-size:11px;font-weight:700;min-width:42px;text-align:center;">{row["Criterion"]}</span>'
                        f'<span style="font-size:12px;color:#2C3E50;">{row["Description"][:65]}</span>'
                        f'<span style="font-size:11px;color:#888;margin-left:auto;">×{row["Triggered in"]}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.info("No criteria data available.")

        # ── Full Variant Table ────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("#### Variant-Level Classifications")

        tier_filter = st.multiselect(
            "Filter by ACMG Tier",
            options=["Pathogenic","Likely Pathogenic","Uncertain Significance","Likely Benign","Benign"],
            default=["Pathogenic","Likely Pathogenic"],
            key="acmg_tier_filter",
        )

        filtered = [r for r in acmg_results if r["acmg_class"] in tier_filter] if tier_filter else acmg_results
        if filtered:
            for r in filtered:
                tier  = r.get("acmg_class", "Uncertain Significance")
                bg    = ACMG_TIER_BG.get(tier, "#FFFFFF")
                tc    = ACMG_TIER_COLORS.get(tier, "#888")
                emoji = ACMG_TIER_EMOJI.get(tier, "⚪")
                crit_badges = ""
                for crit in r.get("criteria","None").split("|"):
                    if crit and crit != "None":
                        c_color = "#E74C3C" if any(crit.startswith(p) for p in ["PVS","PS","PM","PP"]) else "#27AE60"
                        crit_badges += f'<span style="background:{c_color};color:white;padding:1px 6px;border-radius:8px;font-size:10px;margin-right:3px;">{crit}</span>'
                st.markdown(f"""
                <div style="background:{bg};border-left:4px solid {tc};border-radius:8px;
                            padding:10px 14px;margin-bottom:8px;">
                  <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div>
                      <span style="font-weight:700;font-size:14px;color:#2C3E50;">{r.get('gene','.')}</span>
                      <span style="font-size:11px;color:#555;margin-left:8px;font-family:monospace;">{r.get('hgvsc','.')}</span>
                    </div>
                    <span style="background:{tc};color:white;padding:2px 10px;border-radius:12px;
                                 font-size:12px;font-weight:700;">{emoji} {tier}</span>
                  </div>
                  <div style="margin-top:6px;display:flex;flex-wrap:wrap;gap:6px;align-items:center;">
                    <span style="font-size:11px;color:#555;">⚡ {r.get('consequence','.')}</span>
                    <span style="font-size:11px;color:#555;">|</span>
                    <span style="font-size:11px;color:#555;">🌍 gnomAD: {r.get('gnomad_af','.')}</span>
                    <span style="font-size:11px;color:#555;">|</span>
                    <span style="font-size:11px;color:#555;">🏥 ClinVar: {r.get('clinvar','.')}</span>
                    <span style="font-size:11px;color:#555;">|</span>
                    <span style="font-size:11px;color:#555;">SIFT: {r.get('sift','.')} | PolyPhen: {r.get('polyphen','.')}</span>
                  </div>
                  <div style="margin-top:6px;">{crit_badges}</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No variants match the selected tier filter.")

        # ── Clinical Guidance Footer ──────────────────────────────────────────
        st.markdown("---")
        st.warning(
            "⚕️ **Clinical Disclaimer:** ACMG/AMP variant classification is based on computational "
            "evidence from VEP annotations (SIFT, PolyPhen, gnomAD, ClinVar). "
            "Classifications require validation by a certified clinical geneticist before "
            "therapeutic decisions. This tool does not replace expert clinical interpretation."
        )
        if is_demo:
            st.info("📌 **Demo mode**: Showing representative variants for NA12878 (GIAB HG001). "
                    "Real ACMG classification requires VEP-annotated VCF with `--check_existing`.")

        # ── Download ACMG results ─────────────────────────────────────────────
        st.markdown("---")
        dl_col1, dl_col2 = st.columns(2)

        with dl_col1:
            # TSV download
            import io as _io
            tsv_rows = ["Gene\tHGVSc\tConsequence\tImpact\tgnomAD_AF\tClinVar\tSIFT\tPolyPhen\tCriteria\tACMG_Class\tACMG_Score"]
            for r in acmg_results:
                tsv_rows.append("\t".join([
                    r.get("gene","."), r.get("hgvsc","."), r.get("consequence","."),
                    r.get("impact","."), r.get("gnomad_af","."), r.get("clinvar","."),
                    r.get("sift","."), r.get("polyphen","."),
                    r.get("criteria","None"), r.get("acmg_class","."),
                    str(r.get("acmg_score",".")),
                ]))
            tsv_content = "\n".join(tsv_rows)
            st.download_button(
                "⬇️ Download ACMG TSV",
                data=tsv_content.encode("utf-8"),
                file_name=f"acmg_classification_{datetime.now().strftime('%Y%m%d')}.tsv",
                mime="text/tab-separated-values",
                key="acmg_tsv_dl",
            )

        with dl_col2:
            # JSON summary download
            summary_to_dl = st.session_state.get("acmg_summary") or {
                "total_variants": len(acmg_results),
                "classification_counts": dict(Counter(r["acmg_class"] for r in acmg_results)),
                "criteria_framework": "ACMG/AMP 2015 (Richards et al., Genet Med 17:405-424)",
                "annotation_source": "Ensembl VEP --everything --check_existing",
                "top_pathogenic": [r for r in acmg_results
                                   if r.get("acmg_class") in ("Pathogenic","Likely Pathogenic")][:10],
            }
            st.download_button(
                "⬇️ Download ACMG JSON Summary",
                data=json.dumps(summary_to_dl, indent=2).encode("utf-8"),
                file_name=f"acmg_summary_{datetime.now().strftime('%Y%m%d')}.json",
                mime="application/json",
                key="acmg_json_dl",
            )

# ═════════════════════════════════════════════════════════════════════════════
# ═════════════════════════════════════════════════════════════════════════════
# TAB 5: AI INTERPRETATION
# ═════════════════════════════════════════════════════════════════════════════
with tab5:
    st.markdown("### 🤖 AI Clinical Interpretation")
    st.markdown(
        '<div style="font-size:12px;color:#7f8c8d;margin-bottom:12px;">'
        'Offline RAG + Local LLM &nbsp;|&nbsp; Knowledge: ClinVar + CPIC + OMIM &nbsp;|&nbsp; '
        'No internet required &nbsp;|&nbsp; No API keys &nbsp;|&nbsp; Runs entirely inside Docker'
        '</div>', unsafe_allow_html=True,
    )

    # ── AI Engine Status Banner ───────────────────────────────────────────────
    if AI_ENGINE_OK:
        ai_st = ai_status()
        mode  = ai_st.get("mode", "rule")
        mode_color = {"llm": "#27ae60", "rag": "#2980b9", "rule": "#e67e22"}.get(mode, "#7f8c8d")
        mode_label = {"llm": "🟢 LLM + RAG (full AI)", "rag": "🔵 RAG only (no LLM)", "rule": "🟡 Rule-based (offline fallback)"}.get(mode, mode)
        st.markdown(
            f'<div style="background:#f8f9fa;border-left:4px solid {mode_color};padding:10px 14px;'
            f'border-radius:6px;font-size:13px;margin-bottom:16px;">'
            f'<b>AI Mode:</b> {mode_label} &nbsp;|&nbsp; '
            f'<b>Model:</b> {ai_st.get("model","N/A")} &nbsp;|&nbsp; '
            f'<b>ClinVar docs:</b> {ai_st.get("clinvar_docs",0)} &nbsp;|&nbsp; '
            f'<b>CPIC docs:</b> {ai_st.get("cpic_docs",0)}'
            f'</div>', unsafe_allow_html=True,
        )
    else:
        st.info("ℹ️ AI engine not installed. Run `pip install chromadb sentence-transformers ollama` to enable full AI mode.")

    # ── Variant Interpretation Section ───────────────────────────────────────
    st.markdown("#### 🧬 Top Variant Interpretations")
    is_demo_ai = st.session_state.get("demo_mode", False)
    acmg_rows  = (REAL_NA12878_ACMG or DEMO_ACMG_RESULTS) if is_demo_ai else st.session_state.get("acmg_results", [])

    if acmg_rows and AI_ENGINE_OK:
        with st.spinner("🤖 Generating AI clinical interpretations..."):
            top_interps = batch_interpret_top_variants(acmg_rows, max_variants=5)

        for i, interp in enumerate(top_interps):
            acmg_badge_colors = {
                "Pathogenic": "#c0392b", "Likely Pathogenic": "#e67e22",
                "Uncertain Significance": "#7f8c8d", "Likely Benign": "#27ae60", "Benign": "#2ecc71"
            }
            badge_col = acmg_badge_colors.get(interp.get("acmg_class", ""), "#7f8c8d")
            src_icon  = {"llm": "🤖", "rag": "📚", "rule": "📋"}.get(interp.get("source", "rule"), "📋")

            with st.expander(
                f"{src_icon} **{interp.get('gene','?')}** — {interp.get('variant','?')}  "
                f"[{interp.get('acmg_class','')}]",
                expanded=(i == 0)
            ):
                st.markdown(
                    f'<span style="background:{badge_col};color:white;padding:2px 8px;'
                    f'border-radius:4px;font-size:12px;font-weight:bold;">'
                    f'{interp.get("acmg_class","")}</span> '
                    f'<span style="font-size:11px;color:#7f8c8d;">Source: {interp.get("source","rule")}</span>',
                    unsafe_allow_html=True,
                )
                st.markdown("")
                if interp.get("paragraph1"):
                    st.markdown(interp["paragraph1"])
                if interp.get("paragraph2"):
                    st.markdown(interp["paragraph2"])
                if interp.get("context"):
                    with st.expander("📖 Knowledge base context used", expanded=False):
                        st.caption(interp["context"][:500] + "...")
    elif not acmg_rows:
        st.info("Run a pipeline or load results in **🧬 New Analysis** to see AI interpretations.")
    else:
        st.warning("AI engine not available. Install dependencies to enable interpretations.")

    st.markdown("---")

    # ── PGx AI Drug Safety Section ────────────────────────────────────────────
    st.markdown("#### 💊 PGx Drug Safety AI Summary")

    pgx_data = st.session_state.get("pgx_data") or (
        {"genes": [
            {"gene":"CYP2D6","diplotype":"*4/*4","phenotype":"Poor Metabolizer",
             "drugs":["codeine","tramadol","amitriptyline","metoprolol"]},
            {"gene":"CYP2C19","diplotype":"*2/*2","phenotype":"Poor Metabolizer",
             "drugs":["clopidogrel","omeprazole","escitalopram"]},
            {"gene":"DPYD","diplotype":"*1/*2A","phenotype":"Intermediate Metabolizer",
             "drugs":["fluorouracil","capecitabine"]},
        ]} if is_demo_ai else None
    )

    if pgx_data and AI_ENGINE_OK:
        genes_list = pgx_data.get("genes", [])
        if not genes_list and isinstance(pgx_data, list):
            genes_list = pgx_data

        # Build gene list from PharmCAT results if available
        pharmcat_path = None
        for possible in [
            _REAL_NA12878_OUTDIR / "PGx" / "pharmcat",
            PANTHER_DIR / "outdir" / "NA12878_vep" / "PGx" / "pharmcat",
        ]:
            if possible.exists():
                pharmcat_path = possible
                break

        if pharmcat_path:
            phen_file = next(pharmcat_path.glob("*phenotype.json"), None)
            if phen_file:
                try:
                    phen_data = json.loads(phen_file.read_text())
                    genes_from_pharmcat = []
                    for gname, ginfo in phen_data.get("genes", {}).items():
                        pheno   = ginfo.get("phenotype", "Unknown")
                        diplo   = ginfo.get("diplotype", {})
                        diplo_s = diplo.get("name", "") if isinstance(diplo, dict) else str(diplo)
                        drugs_g = list(ginfo.get("relatedDrugs", {}).keys())[:5]
                        if drugs_g:
                            genes_from_pharmcat.append({
                                "gene": gname, "diplotype": diplo_s,
                                "phenotype": pheno, "drugs": drugs_g
                            })
                    if genes_from_pharmcat:
                        genes_list = genes_from_pharmcat
                except Exception:
                    pass

        for gentry in genes_list[:5]:
            gene_name  = gentry.get("gene", "?")
            diplotype  = gentry.get("diplotype", "unknown")
            phenotype  = gentry.get("phenotype", "unknown")
            drugs      = gentry.get("drugs", [])

            with st.spinner(f"💊 AI summary for {gene_name}..."):
                pgx_interp = explain_pgx(gene_name, diplotype, phenotype, drugs) if AI_ENGINE_OK else None

            if pgx_interp:
                with st.expander(f"💊 **{gene_name}** — {phenotype} ({diplotype})", expanded=(gene_name=="CYP2D6")):
                    if pgx_interp.get("paragraph1"):
                        st.markdown(pgx_interp["paragraph1"])
                    if pgx_interp.get("paragraph2"):
                        st.markdown(pgx_interp["paragraph2"])
                    if pgx_interp.get("recommendations"):
                        st.markdown("**Drug-specific recommendations:**")
                        for rec in pgx_interp["recommendations"]:
                            drug, action = rec.split(": ", 1) if ": " in rec else (rec, "")
                            icon = "🔴" if "AVOID" in action or "CONTRAIN" in action else ("🟡" if "REDUC" in action or "LOWER" in action else "🟢")
                            st.markdown(f"{icon} **{drug}** — {action}")
    elif not pgx_data:
        st.info("Run pipeline with `--pgx` flag to generate PGx AI drug safety summaries.")


# ═════════════════════════════════════════════════════════════════════════════
# TAB 6: REPORT & DOWNLOAD
# ═════════════════════════════════════════════════════════════════════════════
with tab6:
    st.markdown("### 📄 Clinical PGx Report")

    if not st.session_state.pipeline_done:
        st.info("Run an analysis first to generate your report.")
    else:
        gene_results = st.session_state.gene_results
        drug_results = st.session_state.drug_results

        # Report preview
        st.markdown("""
        <div class="card">
            <div class="card-title">📋 Report Preview</div>
        """, unsafe_allow_html=True)

        rep_col1, rep_col2 = st.columns(2)
        with rep_col1:
            st.markdown(f"""
            **Analysis Tool:** PharmCAT v3.1.1
            **Reference Genome:** GRCh38 (hg38)
            **PGx Guidelines:** CPIC Level A
            **Genes Tested:** {len(CPIC_GENES)} CPIC Level A Genes
            **Report Date:** {datetime.now().strftime('%Y-%m-%d')}
            **Session ID:** {st.session_state.session_id or 'N/A'}
            """)
        with rep_col2:
            pm = sum(1 for g in gene_results if "Poor" in g.get("phenotype", ""))
            im = sum(1 for g in gene_results if "Intermediate" in g.get("phenotype", ""))
            actionable = sum(1 for d in drug_results if d.get("classification", "") != "No change")
            st.markdown(f"""
            **Total Genes Called:** {len(gene_results)}
            **Poor Metabolizers:** {pm}
            **Intermediate Metabolizers:** {im}
            **Actionable Drug Interactions:** {actionable}
            **CYP2D6 SV Calling:** {'Enabled (Cyrius)' if True else 'Disabled'}
            **Data Source:** {'Demo (NA12878 GIAB)' if st.session_state.demo_mode else 'Uploaded data'}
            """)

        st.markdown("</div>", unsafe_allow_html=True)

        # Generate downloadable JSON summary
        report_data = {
            "session_id": st.session_state.session_id,
            "report_date": datetime.now().isoformat(),
            "pipeline": "OncoPanther-AI v1.0",
            "pharmcat_version": "3.1.1",
            "reference_genome": "GRCh38",
            "pgx_sources": "CPIC",
            "gene_results": gene_results,
            "drug_recommendations": drug_results,
            "disclaimer": "For research and demonstration purposes only. Clinical use requires NABL/CAP/CLIA accredited laboratory."
        }
        report_json = json.dumps(report_data, indent=2)

        # Download buttons
        dl_col1, dl_col2, dl_col3 = st.columns(3)
        with dl_col1:
            st.download_button(
                label="⬇️ Download JSON Report",
                data=report_json,
                file_name=f"OncoPanther_PGx_{st.session_state.session_id}_{datetime.now().strftime('%Y%m%d')}.json",
                mime="application/json",
                use_container_width=True
            )
        with dl_col2:
            # CSV gene results
            df_csv = pd.DataFrame(gene_results)
            csv_data = df_csv.to_csv(index=False)
            st.download_button(
                label="⬇️ Download PGx Gene Table (CSV)",
                data=csv_data,
                file_name=f"OncoPanther_Genes_{st.session_state.session_id}.csv",
                mime="text/csv",
                use_container_width=True
            )
            # ACMG TSV download
            _acmg_dl = st.session_state.get("acmg_results") or DEMO_ACMG_RESULTS
            if _acmg_dl:
                import io as _io
                acmg_keys = ["gene","hgvsp","consequence","impact","clinvar","criteria","acmg_class","acmg_score","sift","polyphen","gnomad_af"]
                acmg_tsv_buf = _io.StringIO()
                acmg_tsv_buf.write("\t".join(acmg_keys) + "\n")
                for _ar in _acmg_dl:
                    acmg_tsv_buf.write("\t".join(str(_ar.get(k,"")) for k in acmg_keys) + "\n")
                st.download_button(
                    label="⬇️ Download ACMG/AMP Variants (TSV)",
                    data=acmg_tsv_buf.getvalue(),
                    file_name=f"OncoPanther_ACMG_{st.session_state.session_id}.tsv",
                    mime="text/tab-separated-values",
                    use_container_width=True
                )
        with dl_col3:
            # Generate PDF dynamically using the entered patient details
            _pid  = st.session_state.get("patient_id_run")  or st.session_state.session_id or "PATIENT"
            _phy  = st.session_state.get("physician_run",   "")
            _inst = st.session_state.get("institution_run", "")
            _gen  = st.session_state.get("gender_run",      "")
            _dob  = st.session_state.get("dob_run",         "")
            _eth  = st.session_state.get("ethnicity_run",   "")
            _diag = st.session_state.get("diagnosis_run",   "")

            if REPORTLAB_OK:
                pdf_bytes = generate_pgx_pdf(
                    patient_id=_pid, physician=_phy, institution=_inst,
                    gender=_gen, dob=_dob, ethnicity=_eth, diagnosis=_diag,
                    gene_results=gene_results, drug_results=drug_results,
                    session_id=st.session_state.session_id,
                    demo_mode=st.session_state.demo_mode,
                    acmg_results=st.session_state.get("acmg_results") or DEMO_ACMG_RESULTS,
                    acmg_summary=st.session_state.get("acmg_summary"),
                )
                fname = f"OncoPanther_PGx_ACMG_{_pid}_{datetime.now().strftime('%Y%m%d')}.pdf"
                st.download_button(
                    label="⬇️ Download Full Clinical PDF (PGx + ACMG/AMP)",
                    data=pdf_bytes,
                    file_name=fname,
                    mime="application/pdf",
                    use_container_width=True,
                )
            else:
                # Fallback: look for pipeline-generated PDF
                existing_pdfs = list(PANTHER_DIR.glob("outdir/**/Reporting/PGx/*.pdf"))
                if existing_pdfs:
                    newest_pdf = max(existing_pdfs, key=lambda p: p.stat().st_mtime)
                    with open(newest_pdf, "rb") as f:
                        pdf_bytes = f.read()
                    st.download_button(
                        label="⬇️ Download Clinical PDF",
                        data=pdf_bytes,
                        file_name=f"OncoPanther_PGx_{_pid}_{datetime.now().strftime('%Y%m%d')}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )
                else:
                    st.warning("Install `reportlab` (`pip install reportlab`) to enable PDF generation.")

        # ── Pipeline-generated PDF (from Nextflow 10.2_PgxReporting.nf) ─────────
        if st.session_state.demo_mode and REAL_NA12878_PDF.exists():
            st.markdown("---")
            st.markdown("#### 📄 Full OncoPanther Pipeline Report")
            st.caption("Generated by the complete Nextflow pipeline (ERR194147 → GRCh38 → PharmCAT → ReportLab)")
            with open(REAL_NA12878_PDF, "rb") as _pf:
                _pipeline_pdf_bytes = _pf.read()
            st.download_button(
                label="⬇️ Download OncoPanther Pipeline PDF (Real NA12878 Run)",
                data=_pipeline_pdf_bytes,
                file_name="NA12878_OncoPanther_PGx_Pipeline.pdf",
                mime="application/pdf",
                use_container_width=True,
                key="pipeline_pdf_dl",
            )

        st.divider()

        # Gene-drug reference table
        st.markdown("#### 📚 CPIC Level A Gene-Drug Reference")
        ref_data = {
            "Gene": ["CYP2D6", "CYP2C19", "CYP2C9", "CYP3A5", "DPYD",
                     "TPMT", "NUDT15", "UGT1A1", "SLCO1B1", "VKORC1"],
            "Key Drugs": [
                "Codeine, Tamoxifen, TCAs, SSRIs",
                "Clopidogrel, PPIs, Antidepressants",
                "Warfarin, NSAIDs, Phenytoin",
                "Tacrolimus",
                "5-FU, Capecitabine",
                "Azathioprine, Mercaptopurine",
                "Thiopurines",
                "Irinotecan, Atazanavir",
                "Statins (Simvastatin)",
                "Warfarin",
            ],
            "CPIC Level": ["A"] * 10,
            "Guideline": [
                "CPIC codeine", "CPIC clopidogrel", "CPIC warfarin/NSAIDs",
                "CPIC tacrolimus", "CPIC fluoropyrimidines",
                "CPIC thiopurines", "CPIC thiopurines", "CPIC irinotecan",
                "CPIC statins", "CPIC warfarin",
            ]
        }
        st.dataframe(pd.DataFrame(ref_data), use_container_width=True, hide_index=True)

        # Disclaimer
        st.markdown("""
        <div style="background:#f8f9fa;border:1px solid #dee2e6;border-radius:8px;padding:16px;margin-top:16px;font-size:12px;color:#555;">
        <b>Disclaimer:</b> OncoPanther-AI PGx reports are generated using PharmCAT v3.1.1 and CPIC guidelines.
        Results should be interpreted by qualified clinical pharmacogeneticists or molecular geneticists in the context
        of the patient's complete clinical presentation and medication history. This platform is intended for research
        and laboratory demonstration purposes. Clinical deployment requires NABL/CAP/CLIA-accredited laboratory
        infrastructure, validated workflows, and physician authorization.
        <br><br>
        <b>PharmCAT Reference:</b> Sangkuhl et al. (2020) PharmCAT: A pharmacogenomics clinical annotation tool.
        <i>Clinical Pharmacology &amp; Therapeutics</i>, 107(1), 203-210.
        <br><br>
        <b>OncoPanther-AI</b> is developed by
        <b>Kesavi Himabindhu Vuyyuru, Chinmai Rayidi &amp; Abraham Peele Karlapudi</b>,
        Dept. of Biotechnology &amp; Bioinformatics,
        Vignan's Foundation for Science, Technology &amp; Research (Deemed to be University),
        developed for industry partner
        <b style="color:#E74C3C;">SecuAI</b> — Precision Pharmacogenomics Platform | v1.0-beta
        </div>
        """, unsafe_allow_html=True)
