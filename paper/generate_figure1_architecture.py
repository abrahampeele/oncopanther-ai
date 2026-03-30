"""
Generate Figure 1: OncoPanther-AI Pipeline Architecture
For: OncoPanther-AI manuscript — Briefings in Bioinformatics

Output: paper/figure1_architecture.png (300 DPI, publication quality)

Usage:
    python generate_figure1_architecture.py
"""

import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_PNG    = os.path.join(SCRIPT_DIR, "figure1_architecture.png")

fig, ax = plt.subplots(figsize=(14, 8))
ax.set_xlim(0, 14)
ax.set_ylim(0, 8)
ax.axis('off')

# ── Color palette ─────────────────────────────────────────────────────────────
C_INPUT   = '#1565C0'   # dark blue   — input
C_A       = '#1976D2'   # blue        — alignment/QC
C_B       = '#2E7D32'   # green       — variant calling
C_C       = '#E65100'   # orange      — ACMG classification
C_D       = '#6A1B9A'   # purple      — pharmacogenomics
C_E       = '#00838F'   # teal        — AI narrative
C_OUT     = '#37474F'   # dark grey   — output
C_ARROW   = '#546E7A'
ALPHA_BOX = 0.92

def box(ax, x, y, w, h, color, title, lines, fontsize=8.5, title_fs=9.5):
    """Draw a labelled module box."""
    rect = FancyBboxPatch((x, y), w, h,
                          boxstyle="round,pad=0.08",
                          linewidth=1.3, edgecolor='white',
                          facecolor=color, alpha=ALPHA_BOX,
                          zorder=3)
    ax.add_patch(rect)
    ax.text(x + w/2, y + h - 0.24, title,
            ha='center', va='top', fontsize=title_fs,
            fontweight='bold', color='white', zorder=4)
    for i, line in enumerate(lines):
        ax.text(x + w/2, y + h - 0.55 - i*0.30,
                line, ha='center', va='top',
                fontsize=fontsize, color='#E3F2FD', zorder=4)

def arrow(ax, x1, y1, x2, y2):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=C_ARROW,
                                lw=1.8, connectionstyle='arc3,rad=0.0'),
                zorder=2)

# ─────────────────────────────────────────────────────────────────────────────
# Row layout (y positions):  top row: Input → A → B(scatter) → C
#                            bottom: D (PGx) and E (AI) feed into Output
# ─────────────────────────────────────────────────────────────────────────────

# ── INPUT ─────────────────────────────────────────────────────────────────────
box(ax, 0.2, 5.8, 2.0, 1.9, C_INPUT, 'INPUT',
    ['FASTQ / BAM / CRAM', 'Patient YAML metadata',
     'Reference GRCh38', 'GIAB truth set (validation)'],
    fontsize=8)

# ── Module A: Alignment & QC ──────────────────────────────────────────────────
box(ax, 2.6, 5.8, 2.4, 1.9, C_A, '(A) Alignment & QC',
    ['BWA-MEM2 alignment', 'GATK MarkDuplicates',
     'FastQC · QualiMap', 'Coverage metrics'],
    fontsize=8)

# ── Module B: Chromosome-scatter variant calling ──────────────────────────────
box(ax, 5.4, 5.8, 2.8, 1.9, C_B, '(B) Scatter Variant Calling',
    ['25× parallel HaplotypeCaller', 'chr1–22, X, Y, MT (2 threads each)',
     'bcftools concat → merged gVCF', '2.9× speedup vs. linear GATK'],
    fontsize=8)

# ── Module C: ACMG classification ────────────────────────────────────────────
box(ax, 8.6, 5.8, 2.8, 1.9, C_C, '(C) ACMG/AMP Classification',
    ['VEP + CADD + SpliceAI + gnomAD', 'ACMG/AMP 2015 rule engine',
     'Pathogenic / LP / VUS / LB / Benign', 'ClinVar · OMIM annotation'],
    fontsize=8)

# ── Module D: Pharmacogenomics ────────────────────────────────────────────────
box(ax, 0.2, 3.3, 3.2, 2.1, C_D, '(D) Pharmacogenomics',
    ['PharmCAT v2 — 24 CPIC tier 1/2 genes', 'CYP2D6 · CYP2C19 · CYP2C9',
     'DPYD · TPMT · SLCO1B1 diplotypes',
     'CPIC drug-dosing recommendations'],
    fontsize=8)

# ── Module E: Offline AI Narrative ───────────────────────────────────────────
box(ax, 3.8, 3.3, 4.2, 2.1, C_E, '(E) Offline AI Narrative Engine',
    ['ChromaDB vector DB (ClinVar + OMIM + CPIC)',
     'Retrieval: top-5 chunks by cosine similarity',
     'LLaMA 3.2 3B (4-bit quantized, CPU/GPU)',
     'No patient data transmitted externally'],
    fontsize=8)

# ── Output ────────────────────────────────────────────────────────────────────
box(ax, 8.4, 3.3, 3.2, 2.1, C_OUT, 'OUTPUT',
    ['Annotated VCF with ACMG class',
     'PGx diplotype + dosing report (PDF)',
     'AI clinical narrative (clinician-reviewed)',
     'Streamlit interactive dashboard'],
    fontsize=8)

# ── Arrows ───────────────────────────────────────────────────────────────────
# Input → A
arrow(ax, 2.2,  6.75, 2.6,  6.75)
# A → B
arrow(ax, 5.0,  6.75, 5.4,  6.75)
# B → C
arrow(ax, 8.2,  6.75, 8.6,  6.75)
# C → D (diagonal down-left)
arrow(ax, 8.6,  6.2,  3.4,  5.4)
# C → E (down)
arrow(ax, 9.7,  5.8,  6.2,  5.4)
# C → Output (down-right)
arrow(ax, 10.8, 5.8, 10.0,  5.4)
# D → Output
arrow(ax, 3.4,  4.35, 8.4,  4.35)
# E → Output
arrow(ax, 8.0,  4.35, 8.4,  4.35)

# ── Title and legend ─────────────────────────────────────────────────────────
ax.text(7.0, 7.85, 'OncoPanther-AI Pipeline Architecture',
        ha='center', va='center', fontsize=14, fontweight='bold', color='#212121')
ax.text(7.0, 7.5, 'End-to-end WGS clinical interpretation · Offline · Containerized (Docker/Singularity)',
        ha='center', va='center', fontsize=9, color='#555555')

# Legend patches
patches = [
    mpatches.Patch(color=C_A, label='(A) Alignment & QC'),
    mpatches.Patch(color=C_B, label='(B) Scatter Variant Calling'),
    mpatches.Patch(color=C_C, label='(C) ACMG Classification'),
    mpatches.Patch(color=C_D, label='(D) Pharmacogenomics'),
    mpatches.Patch(color=C_E, label='(E) AI Narrative Engine'),
]
ax.legend(handles=patches, loc='lower center', ncol=5,
          fontsize=8, framealpha=0.85, bbox_to_anchor=(0.5, 0.01))

# ── Privacy badge ─────────────────────────────────────────────────────────────
badge = FancyBboxPatch((11.5, 1.45), 2.3, 0.65,
                       boxstyle="round,pad=0.1",
                       linewidth=1.2, edgecolor='#00838F',
                       facecolor='#E0F7FA', alpha=0.95, zorder=5)
ax.add_patch(badge)
ax.text(12.65, 1.78, '[OFFLINE] Fully Offline', ha='center', va='center',
        fontsize=9, fontweight='bold', color='#006064', zorder=6)
ax.text(12.65, 1.56, 'No patient data leaves the node',
        ha='center', va='center', fontsize=7.5, color='#00695C', zorder=6)

plt.tight_layout(pad=0.5)
plt.savefig(OUT_PNG, dpi=300, bbox_inches='tight', facecolor='white')
plt.close()
print(f"Figure 1 saved: {OUT_PNG}")
