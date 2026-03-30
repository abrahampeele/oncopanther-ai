#!/usr/bin/env python3
"""
generate_narratives.py — OncoPanther-AI Publication Validation
===============================================================
Selects top 20 clinically relevant variants from the NA12878 ACMG TSV
and generates AI narratives using the offline RAG+LLaMA engine.

If Ollama/LLaMA is not available, falls back to rule-based template
narratives (still clinically meaningful, still evaluatable).

Output:
  /home/crak/demo_uploads/CLI-NA12878/outdir/Validation/NarrativeEval/
    narratives_for_eval.csv   — 20 variants + AI text, ready for Streamlit eval page
    narratives_for_eval.json  — same data as JSON

Usage (inside container):
  python3 /app/panther/paper/generate_narratives.py
"""

import os
import sys
import json
import pandas as pd
import subprocess
from datetime import datetime

# ── Paths ───────────────────────────────────────────────────────────────────
ACMG_TSV   = "/home/crak/demo_uploads/CLI-NA12878/outdir/annotation/acmg/PT-NA12878-001_oncoPanther_acmg.tsv"
OUT_DIR    = "/home/crak/demo_uploads/CLI-NA12878/outdir/Validation/NarrativeEval"
OUT_CSV    = os.path.join(OUT_DIR, "narratives_for_eval.csv")
OUT_JSON   = os.path.join(OUT_DIR, "narratives_for_eval.json")
N_VARIANTS = 20

os.makedirs(OUT_DIR, exist_ok=True)

print(f"[1/4] Loading ACMG TSV: {ACMG_TSV}")
df = pd.read_csv(ACMG_TSV, sep='\t', low_memory=False)
print(f"      Loaded {len(df):,} variants")

# ── Select top 20 clinically interesting variants ───────────────────────────
# Priority: Pathogenic > Likely Pathogenic, then by ACMG score desc
# Exclude benign/likely benign, require gene name present
print("[2/4] Selecting top 20 clinically relevant variants...")

priority_classes = ['Pathogenic', 'Likely Pathogenic', 'Uncertain Significance']
df_filt = df[
    df['acmg_class'].isin(priority_classes) &
    df['gene'].notna() &
    (df['gene'] != '.') &
    df['hgvsc'].notna()
].copy()

# Class ranking
class_rank = {'Pathogenic': 0, 'Likely Pathogenic': 1, 'Uncertain Significance': 2}
df_filt['class_rank'] = df_filt['acmg_class'].map(class_rank).fillna(3)
df_filt['acmg_score_num'] = pd.to_numeric(df_filt['acmg_score'], errors='coerce').fillna(0)
df_filt = df_filt.sort_values(['class_rank', 'acmg_score_num'], ascending=[True, False])

# Take top 20, ensuring variety
selected = df_filt.drop_duplicates('gene').head(N_VARIANTS)
if len(selected) < N_VARIANTS:
    # Fill remaining with more variants from same genes
    extra = df_filt[~df_filt.index.isin(selected.index)].head(N_VARIANTS - len(selected))
    selected = pd.concat([selected, extra])

selected = selected.head(N_VARIANTS).reset_index(drop=True)
print(f"      Selected {len(selected)} variants")
print(f"      Classes: {selected['acmg_class'].value_counts().to_dict()}")

# ── Generate narratives ─────────────────────────────────────────────────────
print("[3/4] Generating AI narratives...")

def ollama_available():
    try:
        result = subprocess.run(['ollama', 'list'], capture_output=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False

def generate_with_ollama(row):
    """Generate narrative using local LLaMA 3.2 via Ollama."""
    prompt = f"""You are a clinical geneticist writing a concise interpretation for a clinical genomics report.
Write 3-4 sentences interpreting this variant for a clinician audience.
Be specific, factual, and clinically actionable. Do not speculate beyond the evidence.

Variant details:
- Gene: {row['gene']}
- Coding change: {row['hgvsc']}
- Protein change: {row.get('hgvsp', 'N/A')}
- Consequence: {row['consequence']}
- ACMG Classification: {row['acmg_class']} (score: {row['acmg_score']})
- ACMG Criteria: {row['criteria']}
- gnomAD AF: {row['gnomad_af']}
- ClinVar: {row.get('clinvar', 'Not in ClinVar')}
- SIFT: {row.get('sift', 'N/A')} | PolyPhen: {row.get('polyphen', 'N/A')}

Write the clinical interpretation:"""

    try:
        result = subprocess.run(
            ['ollama', 'run', 'llama3.2:3b', prompt],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception as e:
        pass
    return None

def generate_template(row):
    """Rule-based template narrative — used as fallback if Ollama unavailable."""
    gene        = row['gene']
    hgvsc       = row['hgvsc']
    hgvsp       = row.get('hgvsp', '')
    csq         = row['consequence'].replace('_', ' ')
    acmg_class  = row['acmg_class']
    criteria    = row['criteria']
    gnomad      = row['gnomad_af']
    clinvar     = row.get('clinvar', '')
    sift        = row.get('sift', '')
    polyphen    = row.get('polyphen', '')

    # ClinVar sentence
    cv_sentence = ""
    if clinvar and clinvar not in ['.', 'nan', '']:
        cv_sentence = f" This variant has been reported in ClinVar as {clinvar.replace('_', ' ').lower()}."

    # Functional prediction sentence
    fp_parts = []
    if sift and sift not in ['.', 'nan', '']:
        fp_parts.append(f"SIFT: {sift.replace('_', ' ')}")
    if polyphen and polyphen not in ['.', 'nan', '']:
        fp_parts.append(f"PolyPhen-2: {polyphen.replace('_', ' ')}")
    fp_sentence = f" In silico predictions: {'; '.join(fp_parts)}." if fp_parts else ""

    # Population frequency sentence
    try:
        af = float(gnomad)
        if af < 0.0001:
            pop_sentence = " This variant is extremely rare in the general population (gnomAD AF <0.01%)."
        elif af < 0.001:
            pop_sentence = f" This variant is rare in the general population (gnomAD AF {af:.4f})."
        else:
            pop_sentence = f" This variant has a population frequency of {af:.4f} in gnomAD."
    except (ValueError, TypeError):
        pop_sentence = " Population frequency data are not available for this variant."

    # Criteria sentence
    criteria_list = criteria.replace('|', ', ') if criteria and criteria != '.' else 'not specified'

    narrative = (
        f"A {csq} variant was identified in {gene} ({hgvsc}"
        + (f"; {hgvsp}" if hgvsp and hgvsp not in ['.', 'nan'] else "")
        + f"), classified as {acmg_class} according to ACMG/AMP 2015 criteria "
        + f"(supporting criteria: {criteria_list})."
        + pop_sentence
        + cv_sentence
        + fp_sentence
        + f" Clinical correlation and family history review are recommended to further assess pathogenicity."
    )
    return narrative

# Determine generation method
use_ollama = ollama_available()
method = "LLaMA 3.2 3B (Ollama)" if use_ollama else "Rule-based template (Ollama unavailable)"
print(f"      Narrative method: {method}")

narratives = []
for i, row in selected.iterrows():
    narrative = None
    if use_ollama:
        narrative = generate_with_ollama(row)
    if not narrative:
        narrative = generate_template(row)

    narratives.append({
        'variant_id':   i + 1,
        'gene':         row['gene'],
        'hgvsc':        row['hgvsc'],
        'hgvsp':        row.get('hgvsp', ''),
        'consequence':  row['consequence'],
        'acmg_class':   row['acmg_class'],
        'acmg_score':   row['acmg_score'],
        'criteria':     row['criteria'],
        'gnomad_af':    row['gnomad_af'],
        'clinvar':      row.get('clinvar', ''),
        'ai_narrative': narrative,
        'method':       method,
        'generated_at': datetime.now().isoformat()
    })
    print(f"      [{i+1:02d}/{N_VARIANTS}] {row['gene']} — {row['acmg_class']}")

# ── Save outputs ─────────────────────────────────────────────────────────────
print(f"[4/4] Saving outputs...")
out_df = pd.DataFrame(narratives)
out_df.to_csv(OUT_CSV, index=False)
out_df.to_json(OUT_JSON, orient='records', indent=2)

print(f"\n{'='*60}")
print(f" Narratives ready for evaluation")
print(f"{'='*60}")
print(f" CSV:  {OUT_CSV}")
print(f" JSON: {OUT_JSON}")
print(f" N:    {len(narratives)} narratives")
print(f" Method: {method}")
print(f"\n Next step:")
print(f"   Open http://localhost:8501 → Narrative Evaluation page")
print(f"   Or run: streamlit run /app/panther/demo_app/app.py")
print(f"{'='*60}")
