// Module files for OncoPanther pipeline
// PGx Report Generator - Parse PharmCAT JSON and generate pharmacogenomics PDF report

process GeneratePgxReport {
    tag "GENERATE PGx PDF REPORT FOR ${metadata.SampleID}"
    publishDir "${params.outdir}/Reporting/PGx/", mode: 'copy'

    conda "reportlab=4.4.1 matplotlib=3.9.1 seaborn=0.13.2 pandas=2.3.1 numpy=1.26.4 qrcode=8.2"
    container "${workflow.containerEngine == 'singularity'
        ? 'docker://firaszemzem/pyreportlab-toolkit:1.0'
        : 'firaszemzem/pyreportlab-toolkit:1.0'}"

    input:
    tuple val(metadata), path(vcFile), path(oncopantherlogo), val(metaYaml), path(pharmcatReportJson), path(pharmcatMatchJson), path(pharmcatPhenotypeJson)

    output:
    path "${metadata.SampleID}_PGx.pdf"
    path "plots/${metadata.SampleID}/*.png", optional: true

    script:
    def metaYamlJson = new groovy.json.JsonBuilder(metaYaml).toString().replace("'", "\\'")

    """
#!/usr/bin/env python

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.platypus import Table, TableStyle
from datetime import datetime
import os
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import qrcode

##################################################################################
# Configuration
##################################################################################

metadata = {
    "SampleID": "${metadata.SampleID}",
    "Sex": "${metadata.Sex}",
    "Dob": "${metadata.Dob}",
    "Ethnicity": "${metadata.Ethnicity}",
    "Diagnosis": "${metadata.Diagnosis}",
    "Identifier": "${metadata.Identifier}"
}

oncopantherlogo = "${oncopantherlogo}"
pharmcat_report_json = "${pharmcatReportJson}"
pharmcat_match_json  = "${pharmcatMatchJson}"
pharmcat_pheno_json  = "${pharmcatPhenotypeJson}"

sample_plot_dir = f"plots/{metadata['SampleID']}"
os.makedirs(sample_plot_dir, exist_ok=True)

pdf_file = f"{metadata['SampleID']}_PGx.pdf"
c = canvas.Canvas(pdf_file, pagesize=letter)
c.setTitle(f"OncoPanther-PGx-Report-{metadata['SampleID']}-{datetime.today().strftime('%Y-%m-%d')}")
width, height = letter

try:
    metaYaml = json.loads('''${metaYamlJson}''')
except Exception as e:
    print(f"Error parsing metaYaml: {e}")
    metaYaml = {
        'physician': {'name': 'N/A', 'specialty': 'N/A', 'contact': {'email': 'N/A', 'phone': 'N/A'}, 'affiliation': 'N/A'},
        'institution': {'name': 'N/A', 'department': 'N/A', 'accreditation': 'N/A', 'address': {}},
        'hpo_terms': []
    }

##################################################################################
# Phenotype Color Mapping
##################################################################################

PHENOTYPE_COLORS = {
    'Poor Metabolizer':          '#E74C3C',
    'Intermediate Metabolizer':  '#F39C12',
    'Normal Metabolizer':        '#27AE60',
    'Rapid Metabolizer':         '#3498DB',
    'Ultrarapid Metabolizer':    '#2980B9',
    'Likely Poor Metabolizer':   '#E74C3C',
    'Likely Intermediate Metabolizer': '#F39C12',
    'Indeterminate':             '#95A5A6',
    'N/A':                       '#BDC3C7',
}

PHENOTYPE_ORDER = {
    'Poor Metabolizer': 0,
    'Likely Poor Metabolizer': 0,
    'Intermediate Metabolizer': 1,
    'Likely Intermediate Metabolizer': 1,
    'Normal Metabolizer': 2,
    'Rapid Metabolizer': 3,
    'Ultrarapid Metabolizer': 4,
    'Indeterminate': -1,
    'N/A': -1,
}

RECOMMENDATION_COLORS = {
    'No change': '#27AE60',
    'Use with caution': '#F39C12',
    'Altered dose': '#F39C12',
    'Avoid': '#E74C3C',
    'default': '#95A5A6',
}

##################################################################################
# Header/Footer (reused from 08.0_Reporting.nf pattern)
##################################################################################

def draw_header_to_footer(c, width, height, metadata, oncopantherlogo):
    oncopanther_text = [("Onco", colors.black), ("P", colors.red), ("anther", colors.black)]
    text = c.beginText(50, height - 50)
    text.setFont("Helvetica-Bold", 14)
    for part, color in oncopanther_text:
        text.setFillColor(color)
        text.textOut(part)
    c.drawText(text)

    c.setStrokeColor(colors.red)
    c.line(30, height - 60, width - 30, height - 60)

    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(colors.black)
    c.drawString(190, height - 107, "FOR CLINICAL USE")

    # Draw OncoPanther-AI logo text instead of image
    logo_x = width - 580
    logo_y = height - 115
    c.setFont("Helvetica-Bold", 22)
    c.setFillColor(colors.black)
    c.drawString(logo_x, logo_y, "Onco")
    c.setFillColor(colors.red)
    c.drawString(logo_x + c.stringWidth("Onco", "Helvetica-Bold", 22), logo_y, "P")
    c.setFillColor(colors.black)
    c.drawString(logo_x + c.stringWidth("OncoP", "Helvetica-Bold", 22), logo_y, "anther")
    c.setFillColor(colors.HexColor('#555555'))
    c.setFont("Helvetica", 14)
    c.drawString(logo_x + c.stringWidth("OncoPanther", "Helvetica-Bold", 22) + 5, logo_y, "-AI")
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.HexColor('#888888'))
    c.drawString(logo_x, logo_y - 14, "Precision Oncology | Clinical Genomics | SecuAI")

    report_date_text = datetime.now().strftime("Report Date: %Y-%m-%d")
    c.setFont("Helvetica", 6)
    c.setFillColor(colors.black)
    c.drawRightString(width - 50, height - 50, report_date_text)

    c.setFont("Times-Roman", 8)
    c.setFillColor(colors.black)

    identifier = metadata["Identifier"]
    c.drawString(width - 200, height - 80, f"Identifier: {identifier}")
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.5)
    c.line(width - 200, height - 85, width - 30, height - 85)

    start_x = width - 200
    start_y = height - 100
    patient_info = {
        "Sample ID": metadata["SampleID"],
        "Sex": metadata["Sex"],
        "Date of Birth": metadata["Dob"],
        "Ethnicity": metadata["Ethnicity"],
        "Diagnosis": metadata["Diagnosis"]
    }
    info_items = list(patient_info.items())
    for i in range(0, len(info_items), 2):
        key1, value1 = info_items[i]
        c.drawString(start_x, start_y, f"{key1}: {value1}")
        if i + 1 < len(info_items):
            key2, value2 = info_items[i + 1]
            c.drawString(start_x + 100, start_y, f"{key2}: {value2}")
        start_y -= 15

    footer_y = 40
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.HexColor('#808080'))
    disclaimerText = "Disclaimer: PGx findings should be interpreted by qualified professionals in the context of the patient's clinical presentation and medication history."
    c.drawString(30, 55, disclaimerText)
    c.setStrokeColor(colors.black)
    c.line(30, 50, width - 30, 50)

    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8)
    c.drawString(30, 40, f"OncoPanther PGx | PharmCAT v3.1.1 | CPIC Level A | Page {c.getPageNumber()}")

    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data("https://github.com/SecuAI/OncoPanther-AI")
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    qr_img.save("oncopanther_qr.png")
    c.drawImage("oncopanther_qr.png", width - 80, 20, width=50, height=50)
    os.remove("oncopanther_qr.png")

##################################################################################
# Parse PharmCAT JSON
##################################################################################

def parse_pharmcat_report(report_json_path):
    with open(report_json_path) as f:
        data = json.load(f)

    gene_results = []
    genes_data = data.get('genes', {})
    if isinstance(genes_data, dict):
        genes_iter = genes_data.values()
    else:
        genes_iter = genes_data

    for gene_data in genes_iter:
        if isinstance(gene_data, str):
            continue
        diplotypes = gene_data.get('sourceDiplotypes', [])
        if diplotypes and isinstance(diplotypes[0], dict):
            diplotype_str = diplotypes[0].get('label', 'N/A')
        else:
            diplotype_str = 'N/A'

        phenotypes = []
        for sd in diplotypes:
            if isinstance(sd, dict):
                for p in sd.get('phenotypes', []):
                    if p and p != 'No Result':
                        phenotypes.append(p)
        phenotype_str = phenotypes[0] if phenotypes else 'N/A'

        activity_score = None
        for sd in diplotypes:
            if isinstance(sd, dict) and sd.get('activityScore') is not None:
                activity_score = sd.get('activityScore')
                break

        gene_results.append({
            'gene': gene_data.get('geneSymbol', gene_data.get('gene', '')),
            'diplotype': diplotype_str,
            'phenotype': phenotype_str,
            'activityScore': str(activity_score) if activity_score is not None else 'N/A',
        })

    drug_recommendations = []
    drugs_data = data.get('drugs', data.get('drugRecommendations', {}))
    if isinstance(drugs_data, dict):
        for source_name, source_drugs in drugs_data.items():
            if not isinstance(source_drugs, dict):
                continue
            for drug_name, drug_info in source_drugs.items():
                if not isinstance(drug_info, dict):
                    continue
                for guideline in drug_info.get('guidelines', []):
                    for annotation in guideline.get('annotations', []):
                        drug_rec = annotation.get('drugRecommendation', 'N/A')
                        classification = annotation.get('classification', 'N/A')
                        ann_genes = [g.get('gene', '') for g in annotation.get('genes', []) if isinstance(g, dict)]
                        if not ann_genes:
                            ann_genes = [drug_name]
                        drug_recommendations.append({
                            'drug': drug_name,
                            'genes': ', '.join(ann_genes) if ann_genes else 'N/A',
                            'classification': str(classification) if classification else 'N/A',
                            'recommendation': str(drug_rec) if drug_rec else 'N/A',
                            'source': source_name,
                        })
    elif isinstance(drugs_data, list):
        for drug_data in drugs_data:
            drug_name = drug_data.get('drug', {}).get('name', '')
            genes = [g.get('gene', '') for g in drug_data.get('genes', [])]
            recs = drug_data.get('recommendations', [])
            for rec in recs:
                drug_recommendations.append({
                    'drug': drug_name,
                    'genes': ', '.join(genes),
                    'classification': rec.get('classification', 'N/A'),
                    'recommendation': rec.get('drugRecommendation', 'N/A'),
                    'source': rec.get('source', 'N/A'),
                })

    return gene_results, drug_recommendations

gene_results, drug_recommendations = parse_pharmcat_report(pharmcat_report_json)

##################################################################################
# PAGE 1: PGx Summary Dashboard
##################################################################################

draw_header_to_footer(c, width, height, metadata, oncopantherlogo)

# Title
c.setFont("Helvetica-Bold", 14)
c.setFillColor(colors.HexColor('#C0392B'))
c.drawCentredString(width/2, height - 170, "PHARMACOGENOMICS (PGx) REPORT")

c.setFont("Helvetica", 9)
c.setFillColor(colors.black)
c.drawCentredString(width/2, height - 185, "CPIC Level A Gene Analysis - PharmCAT v3.1.1")

# Physician Info
xpos_left = 50
ypos = height - 210
c.setFont("Helvetica-Bold", 9)
c.drawString(xpos_left, ypos, "Physician:")
c.setFont("Helvetica", 8)
physician_name = metaYaml.get('physician', {}).get('name', 'N/A')
physician_specialty = metaYaml.get('physician', {}).get('specialty', 'N/A')
c.drawString(xpos_left + 70, ypos, f"{physician_name} | {physician_specialty}")
ypos -= 15

c.setFont("Helvetica-Bold", 9)
c.drawString(xpos_left, ypos, "Institution:")
c.setFont("Helvetica", 8)
institution_name = metaYaml.get('institution', {}).get('name', 'N/A')
c.drawString(xpos_left + 70, ypos, institution_name)
ypos -= 25

# Vertical line
c.setStrokeColor(colors.red)
c.line(125, height - 160, 125, 60)

# Gene Summary Table
c.setFont("Courier-BoldOblique", 10)
c.drawString(50, ypos, "Gene Summary")
ypos -= 5

# Table data
table_data = [['Gene', 'Diplotype', 'Phenotype', 'Activity Score']]
for gr in gene_results:
    table_data.append([gr['gene'], gr['diplotype'], gr['phenotype'], gr['activityScore']])

if len(gene_results) == 0:
    table_data.append(['No PGx results available', '', '', ''])

col_widths = [70, 100, 160, 80]
row_height = 15

# Draw table header
start_x = 50
header_y = ypos - 15
c.setFont("Helvetica-Bold", 8)
c.setFillColor(colors.white)
table_width = sum(col_widths)
c.setFillColor(colors.HexColor('#2C3E50'))
c.rect(start_x, header_y, table_width, row_height, fill=1, stroke=1)
c.setFillColor(colors.white)
for i, (col, w) in enumerate(zip(table_data[0], col_widths)):
    c.drawCentredString(start_x + sum(col_widths[:i]) + w/2, header_y + 4, col)

# Draw data rows
c.setFont("Helvetica", 7)
for row_idx, row in enumerate(table_data[1:], start=1):
    y = header_y - row_idx * row_height
    phenotype = row[2] if len(row) > 2 else ''
    bg_color = PHENOTYPE_COLORS.get(phenotype, '#FFFFFF')
    c.setFillColor(colors.HexColor(bg_color))
    c.rect(start_x, y, table_width, row_height, fill=1, stroke=1)
    c.setFillColor(colors.black)
    for i, (cell, w) in enumerate(zip(row, col_widths)):
        text = str(cell) if cell else ''
        # Truncate long phenotype text
        if i == 2 and len(text) > 30:
            text = text[:28] + '..'
        c.drawCentredString(start_x + sum(col_widths[:i]) + w/2, y + 4, text)

    # Check if we need a new page
    if y < 80:
        c.showPage()
        draw_header_to_footer(c, width, height, metadata, oncopantherlogo)
        header_y = height - 170
        c.setFont("Helvetica", 7)

##################################################################################
# PAGE 2: Metabolizer Status Visualization
##################################################################################

c.showPage()
draw_header_to_footer(c, width, height, metadata, oncopantherlogo)

c.setFont("Helvetica-Bold", 12)
c.setFillColor(colors.HexColor('#C0392B'))
c.drawCentredString(width/2, height - 170, "Metabolizer Status Overview")

# Create metabolizer heatmap plot
def create_metabolizer_plot(gene_results, sample_plot_dir, sample_id):
    genes_with_phenotype = [g for g in gene_results if g['phenotype'] not in ['N/A', '', None]]

    if not genes_with_phenotype:
        fig, ax = plt.subplots(figsize=(8, 3))
        ax.text(0.5, 0.5, 'No metabolizer phenotypes available', ha='center', va='center', fontsize=14)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        plot_path = os.path.join(sample_plot_dir, f"{sample_id}_metabolizer_status.png")
        plt.savefig(plot_path, bbox_inches='tight', dpi=200)
        plt.close()
        return plot_path

    genes = [g['gene'] for g in genes_with_phenotype]
    phenotypes = [g['phenotype'] for g in genes_with_phenotype]
    bar_colors = [PHENOTYPE_COLORS.get(p, '#BDC3C7') for p in phenotypes]
    positions = [PHENOTYPE_ORDER.get(p, -1) for p in phenotypes]

    fig, ax = plt.subplots(figsize=(10, max(4, len(genes) * 0.5)))

    y_pos = np.arange(len(genes))
    bars = ax.barh(y_pos, [max(p, 0.3) for p in positions], color=bar_colors, edgecolor='white', height=0.6)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(genes, fontsize=9, fontweight='bold')
    ax.set_xlabel('Metabolizer Spectrum', fontsize=10)
    ax.set_title(f'Metabolizer Status - {sample_id}', fontsize=12, fontweight='bold')

    ax.set_xticks([0, 1, 2, 3, 4])
    ax.set_xticklabels(['PM', 'IM', 'NM', 'RM', 'UM'], fontsize=9)
    ax.set_xlim(-0.5, 5)

    # Add phenotype labels on bars
    for i, (bar, pheno) in enumerate(zip(bars, phenotypes)):
        label = pheno.replace(' Metabolizer', '').replace('Likely ', 'L-')
        ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height()/2, label,
                va='center', fontsize=7, color='#333333')

    # Legend
    legend_patches = [
        mpatches.Patch(color='#E74C3C', label='Poor'),
        mpatches.Patch(color='#F39C12', label='Intermediate'),
        mpatches.Patch(color='#27AE60', label='Normal'),
        mpatches.Patch(color='#3498DB', label='Rapid'),
        mpatches.Patch(color='#2980B9', label='Ultrarapid'),
    ]
    ax.legend(handles=legend_patches, loc='lower right', fontsize=7, framealpha=0.8)

    ax.invert_yaxis()
    plt.tight_layout()

    plot_path = os.path.join(sample_plot_dir, f"{sample_id}_metabolizer_status.png")
    plt.savefig(plot_path, bbox_inches='tight', dpi=200)
    plt.close()
    return plot_path

metabolizer_plot = create_metabolizer_plot(gene_results, sample_plot_dir, metadata['SampleID'])

plot_width = 450
plot_height = min(350, max(150, len(gene_results) * 25))
plot_x = (width - plot_width) / 2
plot_y = height - 200 - plot_height
c.drawImage(metabolizer_plot, plot_x, plot_y, width=plot_width, height=plot_height, preserveAspectRatio=True)

##################################################################################
# PAGE 3+: Gene-Drug Interaction Table & Recommendations
##################################################################################

c.showPage()
draw_header_to_footer(c, width, height, metadata, oncopantherlogo)

c.setFont("Helvetica-Bold", 12)
c.setFillColor(colors.HexColor('#C0392B'))
c.drawCentredString(width/2, height - 170, "Drug Recommendations")

c.setFont("Helvetica", 8)
c.setFillColor(colors.black)
c.drawCentredString(width/2, height - 185, "Based on CPIC Clinical Pharmacogenetics Guidelines")

ypos = height - 210

if not drug_recommendations:
    c.setFont("Helvetica-Oblique", 10)
    c.setFillColor(colors.HexColor('#95A5A6'))
    c.drawCentredString(width/2, ypos - 30, "No actionable drug recommendations found for this patient.")
else:
    # Drug recommendations table
    rec_table_data = [['Drug', 'Gene(s)', 'Classification', 'Recommendation']]
    for rec in drug_recommendations:
        # Truncate long recommendation text
        rec_text = rec['recommendation']
        if len(rec_text) > 80:
            rec_text = rec_text[:77] + '...'
        rec_table_data.append([
            rec['drug'],
            rec['genes'],
            rec['classification'],
            rec_text
        ])

    rec_col_widths = [80, 60, 70, 310]
    rec_row_height = 28

    # Header
    start_x = 40
    header_y = ypos - 10
    c.setFont("Helvetica-Bold", 7)
    rec_table_width = sum(rec_col_widths)
    c.setFillColor(colors.HexColor('#2C3E50'))
    c.rect(start_x, header_y, rec_table_width, 15, fill=1, stroke=1)
    c.setFillColor(colors.white)
    for i, (col, w) in enumerate(zip(rec_table_data[0], rec_col_widths)):
        c.drawCentredString(start_x + sum(rec_col_widths[:i]) + w/2, header_y + 4, col)

    # Data rows
    c.setFont("Helvetica", 6)
    current_y = header_y
    for row_idx, row in enumerate(rec_table_data[1:], start=1):
        y = current_y - row_idx * rec_row_height

        # Check page break
        if y < 80:
            c.showPage()
            draw_header_to_footer(c, width, height, metadata, oncopantherlogo)
            c.setFont("Helvetica-Bold", 10)
            c.setFillColor(colors.HexColor('#C0392B'))
            c.drawCentredString(width/2, height - 170, "Drug Recommendations (continued)")
            current_y = height - 190
            y = current_y - rec_row_height

            # Redraw header
            c.setFont("Helvetica-Bold", 7)
            c.setFillColor(colors.HexColor('#2C3E50'))
            c.rect(start_x, current_y, rec_table_width, 15, fill=1, stroke=1)
            c.setFillColor(colors.white)
            for i, (col, w) in enumerate(zip(rec_table_data[0], rec_col_widths)):
                c.drawCentredString(start_x + sum(rec_col_widths[:i]) + w/2, current_y + 4, col)
            row_idx = 1
            y = current_y - rec_row_height
            current_y = current_y

        # Row background based on classification
        classification = row[2] if len(row) > 2 else ''
        if 'avoid' in classification.lower() or 'contraindicated' in classification.lower():
            bg = '#FADBD8'
        elif 'caution' in classification.lower() or 'alter' in classification.lower():
            bg = '#FEF9E7'
        else:
            bg = '#EAFAF1'

        c.setFillColor(colors.HexColor(bg))
        c.rect(start_x, y, rec_table_width, rec_row_height, fill=1, stroke=1)
        c.setFillColor(colors.black)

        c.setFont("Helvetica-Bold", 6)
        c.drawString(start_x + 4, y + rec_row_height - 10, str(row[0]))

        c.setFont("Helvetica", 6)
        c.drawCentredString(start_x + rec_col_widths[0] + rec_col_widths[1]/2, y + rec_row_height - 10, str(row[1]))
        c.drawCentredString(start_x + rec_col_widths[0] + rec_col_widths[1] + rec_col_widths[2]/2, y + rec_row_height - 10, str(row[2]))

        # Wrap recommendation text
        rec_text = str(row[3])
        rec_x = start_x + rec_col_widths[0] + rec_col_widths[1] + rec_col_widths[2] + 4
        max_chars_per_line = 65
        lines = [rec_text[i:i+max_chars_per_line] for i in range(0, len(rec_text), max_chars_per_line)]
        for line_idx, line in enumerate(lines[:3]):
            c.drawString(rec_x, y + rec_row_height - 10 - (line_idx * 8), line)

##################################################################################
# FINAL PAGE: PGx Methodology
##################################################################################

c.showPage()
draw_header_to_footer(c, width, height, metadata, oncopantherlogo)

c.setFont("Helvetica-Bold", 12)
c.setFillColor(colors.HexColor('#C0392B'))
c.drawCentredString(width/2, height - 170, "PGx Analysis Methodology")

ypos = height - 200

# Vertical line
c.setStrokeColor(colors.red)
c.line(125, height - 160, 125, 60)

sections = [
    ("Analysis Tool", "PharmCAT v3.1.1 (Pharmacogenomics Clinical Annotation Tool)"),
    ("Reference Guidelines", "Clinical Pharmacogenetics Implementation Consortium (CPIC)"),
    ("Reference Genome", "GRCh38 (hg38)"),
    ("Recommendation Sources", "${params.pgxSources ?: 'CPIC'}"),
    ("Analysis Date", datetime.now().strftime("%Y-%m-%d")),
]

c.setFont("Helvetica-Bold", 9)
for label, value in sections:
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(50, ypos, f"{label}:")
    c.setFont("Helvetica", 8)
    c.drawString(200, ypos, value)
    ypos -= 18

ypos -= 15

# Genes Tested
c.setFont("Helvetica-Bold", 9)
c.setFillColor(colors.black)
c.drawString(50, ypos, "CPIC Level A Genes Tested:")
ypos -= 15

cpic_genes = [
    ("CYP2D6", "Opioids, antidepressants, tamoxifen"),
    ("CYP2C19", "Clopidogrel, PPIs, antidepressants"),
    ("CYP2C9", "Warfarin, NSAIDs, phenytoin"),
    ("CYP3A5", "Tacrolimus"),
    ("CYP4F2", "Warfarin"),
    ("CYP2B6", "Efavirenz"),
    ("DPYD", "Fluoropyrimidines (5-FU, capecitabine)"),
    ("TPMT", "Thiopurines (azathioprine, mercaptopurine)"),
    ("NUDT15", "Thiopurines"),
    ("UGT1A1", "Irinotecan, atazanavir"),
    ("SLCO1B1", "Statins (simvastatin)"),
    ("VKORC1", "Warfarin"),
    ("IFNL3", "Peginterferon alfa-2a/2b"),
    ("RYR1", "Volatile anesthetics"),
    ("CACNA1S", "Volatile anesthetics"),
    ("G6PD", "Rasburicase"),
    ("MT-RNR1", "Aminoglycosides"),
    ("NAT2", "Isoniazid"),
    ("HLA-A", "Carbamazepine, allopurinol"),
    ("HLA-B", "Abacavir, carbamazepine, phenytoin"),
]

c.setFont("Helvetica", 7)
col1_x = 70
col2_x = 300
for i, (gene, drugs) in enumerate(cpic_genes):
    if i < 10:
        c.drawString(col1_x, ypos - i * 12, f"{gene}: {drugs}")
    else:
        c.drawString(col2_x, ypos - (i - 10) * 12, f"{gene}: {drugs}")

ypos -= max(10, len(cpic_genes) // 2) * 12 + 20

# Limitations
c.setFont("Helvetica-Bold", 9)
c.setFillColor(colors.HexColor('#C0392B'))
c.drawString(50, ypos, "Limitations:")
ypos -= 15

limitations = [
    "CYP2D6 structural variants (gene deletions, duplications, hybrid alleles) require",
    "  supplementary analysis using specialized tools (e.g., Stargazer, Cyrius).",
    "Whole Exome Sequencing (WES) data may miss intronic PGx variants that affect",
    "  gene function. Whole Genome Sequencing (WGS) provides more complete coverage.",
    "Pharmacogenomic results should be interpreted by qualified clinical professionals",
    "  in the context of the patient's complete clinical presentation and medication history.",
    "This analysis covers germline variants only; somatic or tumor-specific variants",
    "  are not assessed.",
    "Absence of a variant call does not exclude the presence of a clinically relevant allele.",
    "Drug interactions, organ function, and other clinical factors should also be considered.",
]

c.setFont("Helvetica", 7)
c.setFillColor(colors.black)
for i, line in enumerate(limitations):
    c.drawString(70, ypos - i * 11, line)

##################################################################################
# Save PDF
##################################################################################

c.save()
print(f"PGx report generated: {pdf_file}")
    """
}
