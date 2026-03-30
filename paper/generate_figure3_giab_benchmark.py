"""
Generate Figure 3: GIAB Accuracy Benchmark
For: OncoPanther-AI manuscript — Briefings in Bioinformatics

Input:  paper/giab_benchmark_table.csv
Output: paper/figure3_giab_benchmark.png (300 DPI, publication quality)

Usage:
    python generate_figure3_giab_benchmark.py
"""

import os
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IN_CSV  = os.path.join(SCRIPT_DIR, "giab_benchmark_table.csv")
OUT_PNG = os.path.join(SCRIPT_DIR, "figure3_giab_benchmark.png")

df = pd.read_csv(IN_CSV)
print(df.to_string(index=False))

# ── Figure layout: 1 row × 2 cols (SNP | INDEL) ──────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(10, 5))
fig.suptitle(
    "OncoPanther-AI Variant Calling Accuracy\n"
    "vs. GIAB HG001 NISTv3.3.2 Truth Set (GRCh38, 5× WGS demo)",
    fontsize=12, fontweight='bold'
)

metrics    = ['Precision', 'Recall', 'F1']
bar_colors = ['#1976D2', '#43A047', '#FB8C00']
x          = np.arange(len(metrics))
bar_width  = 0.5

for ax, vtype in zip(axes, ['SNP', 'INDEL']):
    row    = df[df['Type'] == vtype].iloc[0]
    values = [row['Precision'], row['Recall'], row['F1']]

    bars = ax.bar(x, values, width=bar_width, color=bar_colors,
                  edgecolor='black', linewidth=0.8)

    # Annotate each bar
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.012,
            f'{val:.3f}',
            ha='center', va='bottom', fontsize=10, fontweight='bold'
        )

    ax.set_xticks(x)
    ax.set_xticklabels(metrics, fontsize=11)
    ax.set_ylabel('Score', fontsize=11)
    ax.set_ylim(0.0, 1.08)
    ax.set_title(f'{vtype} Performance', fontsize=11, fontweight='bold')
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    ax.set_axisbelow(True)

    # Add note about 5x coverage for low recall
    ax.text(
        0.5, 0.04,
        f"5× WGS demo coverage\n"
        f"Truth variants: {row['Truth_Variants']:,}   "
        f"Called: {row['Query_Variants']:,}",
        ha='center', va='bottom', transform=ax.transAxes,
        fontsize=7.5, color='#555555',
        bbox=dict(boxstyle='round,pad=0.3', facecolor='#f5f5f5', alpha=0.7)
    )

plt.tight_layout()
plt.savefig(OUT_PNG, dpi=300, bbox_inches='tight', facecolor='white')
plt.close()
print(f"\nFigure 3 saved: {OUT_PNG}")
