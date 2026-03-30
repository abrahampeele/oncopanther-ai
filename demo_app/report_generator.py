"""
OncoPanther-AI | report_generator.py
Standalone PDF report generation module — NO Streamlit dependency.

Contains:
  - parse_pharmcat_results()
  - parse_acmg_tsv()
  - generate_pgx_pdf()

Can be run directly:
    python3 report_generator.py
"""

import json
import csv
import os
from io import BytesIO
from pathlib import Path
from datetime import datetime

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


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

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
        with open(acmg_files[0], newline="") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                af_raw = row.get("gnomad_af") or row.get("gnomAD_AF") or row.get("MAX_AF") or row.get("max_af") or ""
                try:
                    af_f = float(af_raw) if af_raw not in (".", "", "NA") else None
                    af_display = f"<0.001" if (af_f is not None and af_f < 0.001) else (f"{af_f:.4f}" if af_f else ".")
                except Exception:
                    af_display = af_raw or "."

                sift_label = (row.get("sift") or row.get("SIFT") or ".").split("(")[0].lower() or "."
                poly_label = (row.get("polyphen") or row.get("PolyPhen") or ".").split("(")[0].lower() or "."

                # Handle both lowercase (classify_vcf_bytes output) and UPPERCASE (nf module output)
                def _g(keys, default="."):
                    for k in (keys if isinstance(keys, list) else [keys]):
                        v = row.get(k) or row.get(k.lower()) or row.get(k.upper())
                        if v:
                            return v
                    return default

                results.append({
                    "gene":        _g(["gene", "GENE", "SYMBOL"]),
                    "hgvsc":       _g(["hgvsc", "HGVSc"]),
                    "hgvsp":       _g(["hgvsp", "HGVSp"]),
                    "consequence": (_g(["consequence", "CONSEQUENCE", "Consequence"]) or ".").split("&")[0],
                    "impact":      _g(["impact", "IMPACT"]),
                    "gnomad_af":   af_display,
                    "clinvar":     _g(["clinvar", "ClinVar_CLNSIG", "CLNSIG"]),
                    "criteria":    _g(["criteria", "CRITERIA"], "None"),
                    "acmg_class":  _g(["acmg_class", "ACMG_CLASS"], "Uncertain Significance"),
                    "acmg_score":  _g(["acmg_score", "ACMG_SCORE"], "0"),
                    "sift":        sift_label,
                    "polyphen":    poly_label,
                    "chrom":       _g(["chrom", "CHROM"]),
                    "pos":         _g(["pos", "POS"]),
                    "ref":         _g(["ref", "REF"]),
                    "alt":         _g(["alt", "ALT"]),
                })
    except Exception:
        pass

    return results


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

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

    RED      = colors.HexColor("#E74C3C")
    DARK     = colors.HexColor("#2C3E50")
    LGRAY    = colors.HexColor("#f8f9fa")
    GRIDLINE = colors.HexColor("#dee2e6")

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
        ("BACKGROUND",    (0, 0), (-1, -1), DARK),
        ("TOPPADDING",    (0, 0), (-1,  0), 14),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 14),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
    ]))
    story += [hdr, Spacer(1, 0.4 * cm)]

    # ── Patient information ──────────────────────────────────────────────────
    story.append(Paragraph("Patient Information", sec_title))
    story.append(HRFlowable(width="100%", thickness=2, color=RED, spaceAfter=6))

    rdate = datetime.now().strftime("%d %B %Y")
    src   = "WGS Clinical (NA12878 GIAB)" if demo_mode else "WGS Clinical"
    pat_rows = [
        [Paragraph("Patient ID:",    bold9), Paragraph(str(patient_id),        val9),
         Paragraph("Report Date:",   bold9), Paragraph(rdate,                   val9)],
        [Paragraph("Physician:",     bold9), Paragraph(str(physician or "—"),   val9),
         Paragraph("Session ID:",    bold9), Paragraph(str(session_id or "—"),  val9)],
        [Paragraph("Institution:",   bold9), Paragraph(str(institution or "—"), val9),
         Paragraph("Gender:",        bold9), Paragraph(str(gender or "—"),      val9)],
        [Paragraph("Date of Birth:", bold9), Paragraph(str(dob or "—"),         val9),
         Paragraph("Ethnicity:",     bold9), Paragraph(str(ethnicity or "—"),   val9)],
        [Paragraph("Diagnosis:",     bold9), Paragraph(str(diagnosis or "—"),   val9),
         Paragraph("Data Source:",   bold9), Paragraph(src,                     val9)],
    ]
    pt = Table(pat_rows, colWidths=[3.5 * cm, 5.5 * cm, 3.5 * cm, 5.5 * cm])
    pt.setStyle(TableStyle([
        ("GRID",           (0, 0), (-1, -1), 0.5, GRIDLINE),
        ("ROWPADDING",     (0, 0), (-1, -1), 5),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, LGRAY]),
    ]))
    story += [pt, Spacer(1, 0.3 * cm)]

    # ── Summary metrics ──────────────────────────────────────────────────────
    pm  = sum(1 for g in gene_results if "Poor"         in g.get("phenotype", ""))
    im  = sum(1 for g in gene_results if "Intermediate" in g.get("phenotype", ""))
    nm  = sum(1 for g in gene_results if "Normal"       in g.get("phenotype", ""))
    um  = sum(1 for g in gene_results if "Rapid"        in g.get("phenotype", ""))
    act = sum(1 for d in drug_results if d.get("classification", "") != "No change")

    def big(n, col):
        return Paragraph(f'<font color="{col}" size="18"><b>{n}</b></font>', styles["Normal"])

    def lbl(t):
        return Paragraph(f'<font size="8" color="#7f8c8d">{t}</font>', styles["Normal"])

    met = Table(
        [[big(len(gene_results), "#2C3E50"), big(pm, "#E74C3C"),
          big(im, "#F39C12"),                big(nm, "#27AE60"), big(act, "#E74C3C")],
         [lbl("Genes Called"),               lbl("Poor Met."),
          lbl("Intermediate"),               lbl("Normal Met."), lbl("Actionable Drugs")]],
        colWidths=[3.6 * cm] * 5,
    )
    met.setStyle(TableStyle([
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("GRID",          (0, 0), (-1, -1), 0.5, GRIDLINE),
        ("BACKGROUND",    (0, 0), (-1, -1), colors.white),
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
        ("BACKGROUND", (0, 0), (-1,  0), DARK),
        ("GRID",       (0, 0), (-1, -1), 0.5, GRIDLINE),
        ("ROWPADDING", (0, 0), (-1, -1), 5),
        ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
    ]
    for i, g in enumerate(gene_results, 1):
        pheno = g.get("phenotype", "")
        bg = next((c for k, c in PHENO_BG.items() if k in pheno), colors.white)
        g_rows.append([
            Paragraph(f"<b>{g.get('gene', '')}</b>", ctr9),
            Paragraph(g.get("diplotype", "N/A"), ctr9),
            Paragraph(pheno, ctr9),
            Paragraph(g.get("activity", "N/A"), ctr9),
        ])
        g_styles.append(("BACKGROUND", (0, i), (-1, i), bg))

    gt = Table(g_rows, colWidths=[3 * cm, 4 * cm, 7 * cm, 4 * cm])
    gt.setStyle(TableStyle(g_styles))
    story += [gt, Spacer(1, 0.4 * cm)]

    # ── Drug recommendations ─────────────────────────────────────────────────
    story.append(Paragraph("Drug Dosing Recommendations (CPIC Level A)", sec_title))
    story.append(HRFlowable(width="100%", thickness=2, color=RED, spaceAfter=6))

    d_rows = [[Paragraph(h, sty(f"DH{i}", fontSize=9, fontName="Helvetica-Bold",
                                textColor=colors.white, alignment=TA_CENTER))
               for i, h in enumerate(["Drug", "Gene(s)", "Classification", "Recommendation"])]]
    d_styles = [
        ("BACKGROUND", (0, 0), (-1,  0), DARK),
        ("GRID",       (0, 0), (-1, -1), 0.5, GRIDLINE),
        ("ROWPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN",     (0, 0), (-1, -1), "TOP"),
        ("ALIGN",      (0, 0), ( 2, -1), "CENTER"),
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
        rec = d.get("recommendation", "")
        if len(rec) > 130:
            rec = rec[:127] + "…"
        s8 = sty(f"D8{i}", fontSize=8)
        d_rows.append([
            Paragraph(f"<b>{d.get('drug', '')}</b>", sty(f"DB{i}", fontSize=8, fontName="Helvetica-Bold")),
            Paragraph(d.get("gene", ""), s8),
            Paragraph(cls, s8),
            Paragraph(rec, s8),
        ])
        d_styles.append(("BACKGROUND", (0, i), (-1, i), row_bg))

    dt = Table(d_rows, colWidths=[3 * cm, 3 * cm, 3.5 * cm, 8.5 * cm])
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
            n_tot = acmg_summary.get("total_variants", len(acmg_results))
            TIER_C = {
                "P":  colors.HexColor("#E74C3C"), "LP": colors.HexColor("#E67E22"),
                "VUS": colors.HexColor("#F39C12"), "LB": colors.HexColor("#2ECC71"),
                "B":  colors.HexColor("#27AE60"),
            }

            def acmg_big(n, col):
                return Paragraph(f'<font color="{col.hexval()}" size="16"><b>{n}</b></font>', styles["Normal"])

            def acmg_lbl(t):
                return Paragraph(f'<font size="8" color="#7f8c8d">{t}</font>', styles["Normal"])

            acmg_met = Table(
                [[acmg_big(n_p, TIER_C["P"]),  acmg_big(n_lp, TIER_C["LP"]),
                  acmg_big(n_v, TIER_C["VUS"]), acmg_big(n_lb, TIER_C["LB"]), acmg_big(n_b, TIER_C["B"])],
                 [acmg_lbl("Pathogenic"),        acmg_lbl("Likely Path."),
                  acmg_lbl("VUS"),               acmg_lbl("Likely Benign"), acmg_lbl("Benign")]],
                colWidths=[3.6 * cm] * 5,
            )
            acmg_met.setStyle(TableStyle([
                ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING",    (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("GRID",          (0, 0), (-1, -1), 0.5, GRIDLINE),
                ("BACKGROUND",    (0, 0), (-1, -1), colors.white),
            ]))
            story += [acmg_met, Spacer(1, 0.3 * cm)]

        # Variant table (top 30 — P/LP/VUS first)
        ACMG_TIER_BG_PDF = {
            "Pathogenic":             colors.HexColor("#FADBD8"),
            "Likely Pathogenic":      colors.HexColor("#FDEBD0"),
            "Uncertain Significance": colors.HexColor("#FEF9E7"),
            "Likely Benign":          colors.HexColor("#EAFAF1"),
            "Benign":                 colors.HexColor("#D5F5E3"),
        }
        display_acmg = acmg_results[:30]
        ah = ["Gene", "HGVSp", "Consequence", "ClinVar", "Criteria", "Class"]
        a_rows = [[Paragraph(h, sty(f"AH{i}", fontSize=8, fontName="Helvetica-Bold",
                                    textColor=colors.white, alignment=TA_CENTER))
                   for i, h in enumerate(ah)]]
        a_styles = [
            ("BACKGROUND", (0, 0), (-1,  0), DARK),
            ("GRID",       (0, 0), (-1, -1), 0.5, GRIDLINE),
            ("ROWPADDING", (0, 0), (-1, -1), 4),
            ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
        ]
        for i, av in enumerate(display_acmg, 1):
            tier_bg = ACMG_TIER_BG_PDF.get(av.get("acmg_class", ""), colors.white)
            hgvsp = av.get("hgvsp", ".")
            if hgvsp and len(hgvsp) > 20:
                hgvsp = "…" + hgvsp[-18:]
            a_rows.append([
                Paragraph(f"<b>{av.get('gene', '.')}</b>", sty(f"AG{i}", fontSize=7, fontName="Helvetica-Bold")),
                Paragraph(hgvsp or ".", sty(f"AP{i}", fontSize=7)),
                Paragraph((av.get("consequence", ".") or ".")[:25], sty(f"AC{i}", fontSize=7)),
                Paragraph((av.get("clinvar", ".") or ".")[:20], sty(f"ACV{i}", fontSize=7)),
                Paragraph(av.get("criteria", ".") or ".", sty(f"ACR{i}", fontSize=7)),
                Paragraph(av.get("acmg_class", ".") or ".", sty(f"ACL{i}", fontSize=7, fontName="Helvetica-Bold")),
            ])
            a_styles.append(("BACKGROUND", (0, i), (-1, i), tier_bg))
        at = Table(a_rows, colWidths=[2.5 * cm, 3.5 * cm, 3.5 * cm, 2.5 * cm, 2.5 * cm, 3.5 * cm])
        at.setStyle(TableStyle(a_styles))
        story += [at, Spacer(1, 0.4 * cm)]
        if len(acmg_results) > 30:
            story.append(Paragraph(
                f"<i>Showing top 30 of {len(acmg_results)} variants. Full results available in downloadable TSV.</i>",
                sty("ACMG_NOTE", fontSize=7, textColor=colors.HexColor("#888888")),
            ))
            story.append(Spacer(1, 0.2 * cm))

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
    story.append(Spacer(1, 0.2 * cm))

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


# ---------------------------------------------------------------------------
# CLI entry point — generates real NA12878 clinical PDF when run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # Real NA12878 paths
    outdir        = Path("/home/crak/demo_uploads/CLI-NA12878/outdir")
    patient_id    = "PT-NA12878-001"
    acmg_patient_id = "PT-NA12878-001_oncoPanther"

    # Clinical metadata
    physician   = "Dr. Abraham Peele Karlapudi"
    institution = "Vignan University / OncoPanther Lab"
    gender      = "Male"
    dob         = "1978-04-26"
    ethnicity   = "South Asian"
    diagnosis   = "WGS Clinical PGx Testing"
    demo_mode   = False
    session_id  = "CLI-NA12878"

    # Output path
    out_pdf = Path("/home/crak/demo_uploads/CLI-NA12878/outdir/Reporting/OncoPanther_NA12878_ClinicalReport_FINAL.pdf")

    print(f"[report_generator] Parsing PharmCAT results from {outdir} ...")
    gene_results, drug_results = parse_pharmcat_results(outdir, patient_id)
    print(f"[report_generator]   -> {len(gene_results)} gene(s), {len(drug_results)} drug recommendation(s)")

    print(f"[report_generator] Parsing ACMG TSV for patient {acmg_patient_id} ...")
    acmg_results = parse_acmg_tsv(outdir, acmg_patient_id)
    print(f"[report_generator]   -> {len(acmg_results)} ACMG variant(s)")

    # Load ACMG summary JSON if available
    acmg_summary = None
    acmg_summary_file = outdir / "annotation" / "acmg" / f"{acmg_patient_id}_acmg_summary.json"
    if acmg_summary_file.exists():
        try:
            with open(acmg_summary_file) as f:
                acmg_summary = json.load(f)
            print(f"[report_generator]   -> ACMG summary loaded from {acmg_summary_file}")
        except Exception as e:
            print(f"[report_generator]   WARNING: could not load ACMG summary: {e}")
    else:
        print(f"[report_generator]   (no ACMG summary JSON at {acmg_summary_file})")

    if not REPORTLAB_OK:
        print("[report_generator] ERROR: ReportLab is not installed. Cannot generate PDF.")
        sys.exit(1)

    print("[report_generator] Generating PDF ...")
    pdf_bytes = generate_pgx_pdf(
        patient_id   = patient_id,
        physician    = physician,
        institution  = institution,
        gender       = gender,
        dob          = dob,
        ethnicity    = ethnicity,
        diagnosis    = diagnosis,
        gene_results = gene_results,
        drug_results = drug_results,
        session_id   = session_id,
        demo_mode    = demo_mode,
        acmg_results = acmg_results or None,
        acmg_summary = acmg_summary,
    )

    if pdf_bytes is None:
        print("[report_generator] ERROR: generate_pgx_pdf returned None.")
        sys.exit(1)

    # Ensure output directory exists
    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    with open(out_pdf, "wb") as f:
        f.write(pdf_bytes)

    size_kb = len(pdf_bytes) / 1024
    print(f"[report_generator] PDF saved to: {out_pdf}")
    print(f"[report_generator] PDF size: {size_kb:.1f} KB ({len(pdf_bytes):,} bytes)")
    print("[report_generator] Done.")
