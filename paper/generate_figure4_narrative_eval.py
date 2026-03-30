"""
Generate Figure 4: AI Narrative Evaluation Box Plots
For: OncoPanther-AI manuscript — Briefings in Bioinformatics

Input:  outdir/Validation/NarrativeEval/narrative_ratings.csv
Output: paper/figure4_narrative_eval.png  (300 DPI, publication quality)

Usage:
    python generate_figure4_narrative_eval.py [path_to_ratings.csv]

If no CSV provided, generates a placeholder figure with expected-range data
so the figure slot is ready for the paper draft.
"""

import sys
import os
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Load ratings or use placeholder ─────────────────────────────────────────
if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
    df = pd.read_csv(sys.argv[1])
    print(f"Loaded {len(df)} ratings from {sys.argv[1]}")
    using_real_data = True
else:
    # Placeholder: realistic expected scores for a validated clinical AI system
    print("No ratings CSV provided — generating placeholder figure.")
    np.random.seed(42)
    n = 40  # simulate 2 evaluators × 20 narratives
    df = pd.DataFrame({
        'accuracy':          np.clip(np.random.normal(4.3, 0.6, n), 1, 5).round().astype(int),
        'clarity':           np.clip(np.random.normal(4.5, 0.5, n), 1, 5).round().astype(int),
        'actionability':     np.clip(np.random.normal(4.1, 0.7, n), 1, 5).round().astype(int),
        'hallucination_risk':np.clip(np.random.normal(4.4, 0.6, n), 1, 5).round().astype(int),
        'overall':           np.clip(np.random.normal(4.3, 0.5, n), 1, 5).round().astype(int),
    })
    using_real_data = False

# ── Compute summary stats ────────────────────────────────────────────────────
dimensions = {
    'accuracy':           'Clinical\nAccuracy',
    'clarity':            'Clarity',
    'actionability':      'Actionability',
    'hallucination_risk': 'Absence of\nHallucination',
    'overall':            'Overall\nQuality',
}

data_by_dim = [df[col].dropna().values for col in dimensions.keys()]
labels = list(dimensions.values())

# ── Figure setup ─────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(9, 5.5))

# Colors: blues/greens for positive dims, orange-red for hallucination (inverted = good)
colors = ['#1976D2', '#43A047', '#FB8C00', '#E53935', '#6A1B9A']

bp = ax.boxplot(data_by_dim, patch_artist=True, notch=False,
                medianprops=dict(color='black', linewidth=2),
                whiskerprops=dict(linewidth=1.2),
                capprops=dict(linewidth=1.2),
                flierprops=dict(marker='o', markersize=4, alpha=0.5))

for patch, color in zip(bp['boxes'], colors):
    patch.set_facecolor(color)
    patch.set_alpha(0.75)

# Overlay individual data points (jittered)
for i, data in enumerate(data_by_dim, start=1):
    jitter = np.random.uniform(-0.18, 0.18, size=len(data))
    ax.scatter(np.full_like(data, i, dtype=float) + jitter, data,
               alpha=0.4, color=colors[i-1], s=18, zorder=3)

# Mean markers
for i, data in enumerate(data_by_dim, start=1):
    ax.scatter(i, np.mean(data), marker='D', color='white',
               edgecolor='black', s=50, zorder=5, linewidth=1.2)

# Axis formatting
ax.set_xticks(range(1, len(labels)+1))
ax.set_xticklabels(labels, fontsize=10)
ax.set_yticks([1, 2, 3, 4, 5])
ax.set_yticklabels(['1\n(Unacceptable)', '2\n(Poor)', '3\n(Acceptable)',
                    '4\n(Good)', '5\n(Excellent)'], fontsize=8)
ax.set_ylabel('Score', fontsize=11)
ax.set_ylim(0.5, 5.5)
ax.grid(axis='y', alpha=0.3, linestyle='--')
ax.set_axisbelow(True)

# Add mean ± SD annotations
for i, data in enumerate(data_by_dim, start=1):
    m, s = np.mean(data), np.std(data)
    ax.text(i, 0.65, f'{m:.2f}±{s:.2f}', ha='center', va='bottom',
            fontsize=8, color='#333333', fontweight='bold')

# Title
data_note = "" if using_real_data else " [PLACEHOLDER — replace with real evaluator data]"
ax.set_title(
    f'Figure 4. Expert Clinician Evaluation of AI-Generated Genomic Narratives\n'
    f'(n={len(df)} ratings, {len(df)//20 if len(df)>=20 else "?"} evaluator(s), 20 narratives){data_note}',
    fontsize=10, fontweight='bold', pad=12
)

# Legend
diamond = mpatches.Patch(facecolor='white', edgecolor='black', label='Mean (◆)')
ax.legend(handles=[diamond], fontsize=8, loc='lower right')

plt.tight_layout()

out_path = os.path.join(OUT_DIR, 'figure4_narrative_eval.png')
plt.savefig(out_path, dpi=300, bbox_inches='tight', facecolor='white')
plt.close()

print(f"\nFigure saved: {out_path}")

# Print summary table for manuscript
print("\nSummary for Table 3:")
print(f"{'Dimension':<25} {'Mean':>6} {'SD':>6} {'Min':>4} {'Max':>4}")
print("-" * 50)
for col, label in dimensions.items():
    d = df[col].dropna()
    print(f"{label.replace(chr(10),' '):<25} {d.mean():>6.2f} {d.std():>6.2f} {d.min():>4.0f} {d.max():>4.0f}")
