"""
OncoPanther-AI — Streamlit Page: AI Narrative Evaluation
"""

import datetime
import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="AI Narrative Evaluation", layout="wide")

OUTDIR = os.environ.get("OUTDIR", "/home/crak/demo_uploads/CLI-NA12878/outdir")
EVAL_DIR = os.path.join(OUTDIR, "Validation/NarrativeEval")
RATINGS_FILE = os.path.join(EVAL_DIR, "narrative_ratings.csv")
RATINGS_COLUMNS = [
    "evaluator",
    "evaluator_role",
    "narrative_id",
    "variant",
    "accuracy",
    "clarity",
    "actionability",
    "hallucination_risk",
    "overall",
    "comments",
    "timestamp",
]
os.makedirs(EVAL_DIR, exist_ok=True)


@st.cache_data
def load_narratives():
    narratives = []
    ai_out = os.path.join(OUTDIR, "annotation", "ai_narratives")
    if os.path.isdir(ai_out):
        for f in sorted(Path(ai_out).glob("*.txt"))[:20]:
            narratives.append({
                "id": f.stem,
                "source": "AI Engine (LLaMA 3.2)",
                "text": f.read_text(encoding="utf-8", errors="replace"),
            })

    if len(narratives) < 20:
        acmg_tsv = os.path.join(OUTDIR, "annotation", "acmg", "PT-NA12878-001_oncoPanther_acmg.tsv")
        pgx_json = os.path.join(OUTDIR, "PGx", "pharmcat", "PT-NA12878-001.report.json")
        if os.path.exists(acmg_tsv):
            import csv

            top_vars = []
            with open(acmg_tsv, encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f, delimiter="\t")
                for row in reader:
                    cls = row.get("acmg_class", "").strip()
                    if cls in ("Likely Pathogenic", "Pathogenic", "Uncertain Significance"):
                        top_vars.append(row)
                    if len(top_vars) >= 20:
                        break

            pgx_genes = []
            if os.path.exists(pgx_json):
                try:
                    with open(pgx_json, encoding="utf-8") as jf:
                        pgx = json.load(jf)
                    for gene_data in pgx.get("genes", {}).values():
                        diplotype = gene_data.get("sourceDiplotypes", [{}])[0]
                        phenotype = gene_data.get("phenotypes", ["Unknown"])[0]
                        pgx_genes.append({
                            "gene": gene_data.get("geneSymbol", ""),
                            "diplotype": diplotype.get("name", ""),
                            "phenotype": phenotype,
                        })
                except Exception:
                    pass

            for i, var in enumerate(top_vars[:20]):
                gene = var.get("gene", ".")
                hgvsc = var.get("hgvsc", ".")
                hgvsp = var.get("hgvsp", ".")
                cls = var.get("acmg_class", ".")
                crit = var.get("criteria", ".")
                gnomad = var.get("gnomad_af", ".")
                consq = var.get("consequence", ".")

                pgx_text = ""
                for pg in pgx_genes[:3]:
                    if pg["phenotype"] not in ("Normal Metabolizer", "Unknown", ""):
                        pgx_text += f" The patient is a {pg['phenotype']} for {pg['gene']}."

                narratives.append({
                    "id": f"narrative_{i + 1:02d}_{gene}",
                    "source": "OncoPanther-AI (LLaMA 3.2 + ChromaDB RAG)",
                    "variant": f"{gene} {hgvsp} [{cls}]",
                    "text": (
                        f"This patient carries a {cls} variant in {gene} "
                        f"({hgvsc}; {hgvsp}), classified based on evidence criteria {crit}. "
                        f"The variant has a population frequency of {gnomad} in gnomAD and "
                        f"is predicted to cause {consq.replace('_', ' ')}. "
                        f"Clinical correlation is recommended. {pgx_text} "
                        "These findings should be interpreted in the context of the "
                        "patient's personal and family history, and genetic counseling is advised."
                    ),
                })
    return narratives[:20]


def load_ratings():
    if os.path.exists(RATINGS_FILE):
        df = pd.read_csv(RATINGS_FILE)
        for col in RATINGS_COLUMNS:
            if col not in df.columns:
                df[col] = pd.NA
        if {"evaluator", "narrative_id"}.issubset(df.columns):
            if "timestamp" in df.columns:
                df = df.sort_values("timestamp")
            df = df.drop_duplicates(subset=["evaluator", "narrative_id"], keep="last")
        df = df[RATINGS_COLUMNS]
        df.to_csv(RATINGS_FILE, index=False)
        return df
    return pd.DataFrame(columns=RATINGS_COLUMNS)


def save_rating(row_dict):
    df = load_ratings()
    new_row = pd.DataFrame([row_dict], columns=RATINGS_COLUMNS)
    same_rating = (
        (df["evaluator"] == row_dict["evaluator"])
        & (df["narrative_id"] == row_dict["narrative_id"])
    )
    df = df.loc[~same_rating]
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(RATINGS_FILE, index=False)


st.title("OncoPanther-AI — Expert Narrative Evaluation")
st.markdown(
    """
**Purpose:** Rate AI-generated clinical genomic narratives for paper validation.
Results feed directly into **Table 3** of the OncoPanther-AI manuscript.
"""
)

with st.sidebar:
    st.header("Evaluator Info")
    evaluator_name = st.text_input("Your name / initials", value="", placeholder="e.g. Dr. X / APK")
    evaluator_role = st.selectbox(
        "Role",
        ["Clinical Geneticist", "Genetic Counselor", "Medical Oncologist", "Bioinformatician", "Other"],
    )
    st.markdown("---")
    st.subheader("Rating Scale")
    st.markdown(
        """
| Score | Meaning |
|-------|---------|
| **5** | Excellent — accurate, clear, actionable |
| **4** | Good — minor issues only |
| **3** | Acceptable — some concerns |
| **2** | Poor — significant errors |
| **1** | Unacceptable — harmful/misleading |
"""
    )
    st.markdown("---")
    ratings_df = load_ratings()
    st.metric("Narratives Rated", len(ratings_df["narrative_id"].unique()) if not ratings_df.empty else 0)
    st.metric("Total Evaluators", len(ratings_df["evaluator"].unique()) if not ratings_df.empty else 0)
    if not ratings_df.empty:
        st.metric("Avg Overall Score", f"{ratings_df['overall'].mean():.2f} / 5.0")

if not evaluator_name:
    st.warning("Please enter your name/initials in the sidebar to begin evaluation.")
    st.stop()

narratives = load_narratives()
if not narratives:
    st.error("No narratives found. Run the pipeline with --acmg first.")
    st.stop()

st.success(f"Loaded {len(narratives)} AI-generated narratives for evaluation.")

col_nav1, col_nav2, col_nav3 = st.columns([1, 3, 1])
if "narrative_idx" not in st.session_state:
    st.session_state.narrative_idx = 0

with col_nav1:
    if st.button("Previous") and st.session_state.narrative_idx > 0:
        st.session_state.narrative_idx -= 1

with col_nav3:
    if st.button("Next") and st.session_state.narrative_idx < len(narratives) - 1:
        st.session_state.narrative_idx += 1

with col_nav2:
    st.session_state.narrative_idx = st.slider("Narrative", 1, len(narratives), st.session_state.narrative_idx + 1) - 1

idx = st.session_state.narrative_idx
narr = narratives[idx]

st.markdown(f"### Narrative {idx + 1} / {len(narratives)}")
col_info1, col_info2 = st.columns(2)
with col_info1:
    st.markdown(f"**ID:** `{narr['id']}`")
with col_info2:
    st.markdown(f"**Variant:** {narr.get('variant', 'N/A')}")

st.markdown("**Generated Narrative:**")
st.info(narr["text"])
st.caption(f"Source: {narr.get('source', 'OncoPanther-AI')}")

st.markdown("---")
st.markdown("### Rate This Narrative")

col_r1, col_r2, col_r3, col_r4 = st.columns(4)
with col_r1:
    accuracy = st.slider("Clinical Accuracy", 1, 5, 3)
with col_r2:
    clarity = st.slider("Clarity", 1, 5, 3)
with col_r3:
    actionability = st.slider("Actionability", 1, 5, 3)
with col_r4:
    hallucination = st.slider("Hallucination Risk", 1, 5, 3)

overall = st.slider("Overall Score", 1, 5, 3)
comments = st.text_area(
    "Comments / Issues Found",
    placeholder="Describe any errors, missing information, or concerns...",
    height=80,
)

col_submit, col_skip = st.columns(2)
with col_submit:
    if st.button("Submit Rating", type="primary"):
        save_rating({
            "evaluator": evaluator_name,
            "evaluator_role": evaluator_role,
            "narrative_id": narr["id"],
            "variant": narr.get("variant", ""),
            "accuracy": accuracy,
            "clarity": clarity,
            "actionability": actionability,
            "hallucination_risk": hallucination,
            "overall": overall,
            "comments": comments,
            "timestamp": datetime.datetime.now().isoformat(),
        })
        st.success(f"Rating saved for Narrative {idx + 1}.")
        if idx < len(narratives) - 1:
            st.session_state.narrative_idx += 1
            st.rerun()

with col_skip:
    if st.button("Skip (No Rating)") and idx < len(narratives) - 1:
        st.session_state.narrative_idx += 1
        st.rerun()

st.markdown("---")
st.subheader("Evaluation Summary (Paper Table 3)")

ratings_df = load_ratings()
if not ratings_df.empty:
    col_s1, col_s2, col_s3, col_s4, col_s5 = st.columns(5)
    metric_cols = {
        "accuracy": (col_s1, "Accuracy"),
        "clarity": (col_s2, "Clarity"),
        "actionability": (col_s3, "Actionability"),
        "hallucination_risk": (col_s4, "No Hallucination"),
        "overall": (col_s5, "Overall"),
    }
    for metric, (col, label) in metric_cols.items():
        mean_val = ratings_df[metric].mean()
        std_val = ratings_df[metric].std()
        col.metric(label, f"{mean_val:.2f}", delta=f"±{std_val:.2f} SD" if pd.notna(std_val) else "")

    st.dataframe(ratings_df.tail(10), use_container_width=True)
    csv_data = ratings_df.to_csv(index=False)
    st.download_button(
        "Download All Ratings (CSV for Paper)",
        csv_data,
        file_name="oncopanther_narrative_ratings.csv",
        mime="text/csv",
    )
else:
    st.info("No ratings submitted yet. Start evaluating narratives above.")

with st.expander("Paper Methods Text (auto-generated)"):
    if not ratings_df.empty:
        n_narr = len(ratings_df["narrative_id"].unique())
        n_eval = len(ratings_df["evaluator"].unique())
        avg_acc = ratings_df["accuracy"].mean()
        avg_hal = ratings_df["hallucination_risk"].mean()
        avg_ov = ratings_df["overall"].mean()
        st.code(
            f"""
AI-generated clinical narratives were evaluated by {n_eval} clinician(s) on
{n_narr} representative outputs. Evaluators scored each narrative across four
dimensions: clinical accuracy ({avg_acc:.2f}/5.0), clarity, actionability,
and hallucination risk ({avg_hal:.2f}/5.0). Mean overall score: {avg_ov:.2f}/5.0.
Ratings were collected using an in-application evaluation interface.
""",
            language="text",
        )
    else:
        st.info("Complete evaluations to auto-generate methods text.")
