"""
OncoPanther-AI Engine
=====================
Fully offline RAG + Local LLM pipeline for clinical variant interpretation.
No internet. No API keys. Runs inside Docker.

Components:
  - ChromaDB vector store (ClinVar + CPIC knowledge, pre-indexed)
  - sentence-transformers embeddings (all-MiniLM-L6-v2, local)
  - Ollama LLM (llama3.2:3b, local CPU inference)
  - Rule-based fallback (always works, no dependencies)
"""

import os
import json
import re
from pathlib import Path

# ── Lazy imports (graceful degradation if not installed) ──────────────────────
try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_OK = True
except ImportError:
    CHROMA_OK = False

try:
    from sentence_transformers import SentenceTransformer
    SBERT_OK = True
except ImportError:
    SBERT_OK = False

try:
    import ollama as _ollama
    OLLAMA_OK = True
except ImportError:
    OLLAMA_OK = False

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent
KNOWLEDGE_DIR  = _HERE / "knowledge_base"
CHROMA_DIR     = _HERE / "chroma_db"
KNOWLEDGE_DIR.mkdir(exist_ok=True)
CHROMA_DIR.mkdir(exist_ok=True)

OLLAMA_MODEL = os.environ.get("ONCOPANTHER_LLM", "llama3.2:3b")
EMBED_MODEL  = "all-MiniLM-L6-v2"

# ─────────────────────────────────────────────────────────────────────────────
# KNOWLEDGE BASE — ClinVar + CPIC seed data (pre-indexed at build time)
# ─────────────────────────────────────────────────────────────────────────────

CLINVAR_SEED = [
    {"id":"cv001","gene":"BRCA1","variant":"c.5266dupC","condition":"Hereditary Breast and Ovarian Cancer",
     "classification":"Pathogenic",
     "text":"BRCA1 c.5266dupC (5382insC) is one of the most common BRCA1 founder mutations. Creates a frameshift and premature stop codon (p.Gln1756ProfsTer74). Associated with 85% lifetime breast cancer risk and 40-60% ovarian cancer risk. Prevalent in Ashkenazi Jewish population. NCCN guidelines recommend risk-reducing salpingo-oophorectomy and enhanced breast surveillance."},
    {"id":"cv002","gene":"BRCA2","variant":"c.5946delT","condition":"Hereditary Breast and Ovarian Cancer",
     "classification":"Pathogenic",
     "text":"BRCA2 c.5946delT causes a frameshift leading to premature protein truncation. Strongly associated with hereditary breast, ovarian, and pancreatic cancer. BRCA2 encodes a DNA repair protein essential for homologous recombination. NCCN guidelines recommend genetic counselling and risk-reducing surgical consultation for carriers."},
    {"id":"cv003","gene":"BRCA1","variant":"c.181T>G","condition":"Hereditary Breast and Ovarian Cancer",
     "classification":"Pathogenic",
     "text":"BRCA1 c.181T>G (p.Cys61Gly) is a missense variant affecting a zinc-binding residue in the RING domain. Functionally impairs BRCA1 ubiquitin ligase activity. Classified Pathogenic in ClinVar with multiple submitters. Associated with significantly elevated breast and ovarian cancer risk."},
    {"id":"cv004","gene":"TP53","variant":"c.817C>T","condition":"Li-Fraumeni Syndrome",
     "classification":"Pathogenic",
     "text":"TP53 c.817C>T (p.Arg273Cys) is a hotspot mutation in the DNA-binding domain. Dominant negative effect on wild-type p53 function. Associated with Li-Fraumeni syndrome. Somatically detected in colorectal, lung, and breast cancers. Germline carriers require intensive multi-cancer surveillance from childhood."},
    {"id":"cv005","gene":"TP53","variant":"c.844C>T","condition":"Li-Fraumeni Syndrome",
     "classification":"Pathogenic",
     "text":"TP53 c.844C>T (p.Arg282Trp) disrupts the L3 loop of the DNA-binding domain. One of six hotspot codons in TP53. Classified Pathogenic with strong functional evidence of loss of transcriptional activation. Associated with Li-Fraumeni syndrome and multiple early-onset cancers."},
    {"id":"cv006","gene":"CFTR","variant":"c.1521_1523delCTT","condition":"Cystic Fibrosis",
     "classification":"Pathogenic",
     "text":"CFTR c.1521_1523delCTT (p.Phe508del, F508del) is the most common cystic fibrosis variant worldwide (70% of CF alleles). Causes misfolding and ER retention of CFTR protein. Eligible for CFTR modulator therapy (elexacaftor/tezacaftor/ivacaftor, Trikafta). Patients should be referred to CF specialist for modulator eligibility assessment."},
    {"id":"cv007","gene":"APOE","variant":"c.388T>C","condition":"Alzheimer Disease risk",
     "classification":"Risk Factor",
     "text":"APOE c.388T>C (p.Cys130Arg, APOE4 allele) increases Alzheimer disease risk 3-4x in heterozygotes and 8-12x in homozygotes. Not deterministic — modulates risk rather than causing disease directly. Genetic counselling recommended before and after testing. Pre-symptomatic APOE4 testing is controversial and context-dependent."},
    {"id":"cv008","gene":"MLH1","variant":"c.676C>T","condition":"Lynch Syndrome",
     "classification":"Pathogenic",
     "text":"MLH1 c.676C>T (p.Arg226*) creates a premature stop codon in the MLH1 mismatch repair gene. Associated with Lynch Syndrome — significantly elevated risk of colorectal, endometrial, ovarian, and other cancers. Annual colonoscopy and endometrial surveillance recommended. Cascade testing of first-degree relatives advised."},
    {"id":"cv009","gene":"MSH2","variant":"c.1147A>G","condition":"Lynch Syndrome",
     "classification":"Likely Pathogenic",
     "text":"MSH2 c.1147A>G (p.Asn383Ser) affects a conserved residue in the DNA binding domain. Functional studies show impaired mismatch repair activity. Multiple ClinVar submissions classify as Likely Pathogenic. Lynch Syndrome surveillance protocols should be implemented pending reclassification."},
    {"id":"cv010","gene":"KRAS","variant":"c.35G>T","condition":"Various cancers",
     "classification":"Pathogenic",
     "text":"KRAS c.35G>T (p.Gly12Val) constitutively activates RAS-MAPK signaling. Detected in ~30% of all cancers. Predicts resistance to EGFR inhibitors in colorectal cancer — anti-EGFR therapy (cetuximab, panitumumab) is contraindicated. KRAS G12C-specific inhibitors (sotorasib) do not apply to G12V. Prognosis generally worse than KRAS wild-type."},
    {"id":"cv011","gene":"EGFR","variant":"c.2573T>G","condition":"Non-small cell lung cancer",
     "classification":"Pathogenic",
     "text":"EGFR c.2573T>G (p.Leu858Arg, L858R) is a sensitizing mutation in exon 21. Predicts response to first-line EGFR TKIs (erlotinib, gefitinib, osimertinib). Present in ~40% of EGFR-mutant NSCLC. Osimertinib (3rd generation) preferred due to CNS penetration and T790M coverage. Standard of care testing in all non-squamous NSCLC."},
    {"id":"cv012","gene":"BRAF","variant":"c.1799T>A","condition":"Various cancers",
     "classification":"Pathogenic",
     "text":"BRAF c.1799T>A (p.Val600Glu, V600E) constitutively activates BRAF kinase. Present in 50% of melanoma, 10% colorectal, 5% NSCLC. Targeted therapy available: vemurafenib (single agent), dabrafenib+trametinib (combination). Predictive biomarker for BRAF inhibitor response. Colorectal BRAF V600E associated with poor prognosis and resistance to anti-EGFR therapy."},
    {"id":"cv013","gene":"PALB2","variant":"c.3323delA","condition":"Hereditary Breast Cancer",
     "classification":"Pathogenic",
     "text":"PALB2 c.3323delA causes frameshift and premature truncation. PALB2 is a BRCA2-binding partner essential for homologous recombination repair. Pathogenic variants associated with 35% lifetime breast cancer risk. NCCN recommends enhanced surveillance with annual breast MRI and mammography. Family cascade testing recommended."},
    {"id":"cv014","gene":"BRCA1","variant":"c.5096G>A","condition":"Hereditary Breast Cancer",
     "classification":"Uncertain Significance",
     "text":"BRCA1 c.5096G>A (p.Arg1699Gln) is classified as VUS by most submitters. Located in the BRCT domain. Functional studies show partial impairment but results are inconclusive. ClinVar shows conflicting interpretations across submitters. Clinical management should not be altered based solely on this VUS. Periodic reclassification review recommended."},
    {"id":"cv015","gene":"ATM","variant":"c.7271T>G","condition":"Hereditary Breast Cancer / Ataxia-Telangiectasia",
     "classification":"Pathogenic",
     "text":"ATM c.7271T>G (p.Val2424Gly) is a well-characterised pathogenic ATM variant. Heterozygous carriers have moderately elevated breast cancer risk (~20-25% lifetime). Homozygous carriers develop Ataxia-Telangiectasia. NCCP recommends enhanced breast surveillance for heterozygous female carriers. Avoid unnecessary radiation exposure."},
]

CPIC_SEED = [
    {"id":"cpic001","gene":"CYP2D6","phenotype":"Poor Metabolizer","drug":"codeine",
     "recommendation":"AVOID","evidence":"Strong",
     "text":"CYP2D6 Poor Metabolizers cannot convert codeine to morphine. No analgesic effect AND risk of accumulation of non-opioid metabolites. CPIC recommends AVOIDING codeine in poor metabolizers. Alternative: use non-opioid analgesics or opioids not metabolized by CYP2D6 such as morphine or hydromorphone."},
    {"id":"cpic002","gene":"CYP2D6","phenotype":"Ultrarapid Metabolizer","drug":"codeine",
     "recommendation":"AVOID","evidence":"Strong",
     "text":"CYP2D6 Ultrarapid Metabolizers convert codeine to morphine excessively fast, causing opioid toxicity and respiratory depression. FDA Black Box Warning. CPIC recommends AVOIDING codeine. Multiple pediatric deaths reported in ultrarapid metabolizer children. Use alternative non-CYP2D6 opioids."},
    {"id":"cpic003","gene":"CYP2D6","phenotype":"Poor Metabolizer","drug":"tramadol",
     "recommendation":"AVOID","evidence":"Strong",
     "text":"Tramadol requires CYP2D6 for conversion to active O-desmethyltramadol (M1). Poor Metabolizers have reduced efficacy and altered toxicity profile. CPIC recommends using an alternative analgesic not metabolized by CYP2D6. Consider NSAIDs or non-opioid alternatives."},
    {"id":"cpic004","gene":"CYP2C19","phenotype":"Poor Metabolizer","drug":"clopidogrel",
     "recommendation":"AVOID — use alternative antiplatelet","evidence":"Strong",
     "text":"Clopidogrel requires CYP2C19 for bioactivation to its active thiol metabolite. Poor Metabolizers have significantly reduced platelet inhibition and increased risk of major adverse cardiovascular events (MACE). CPIC and FDA recommend alternative agents: prasugrel or ticagrelor if no contraindications exist."},
    {"id":"cpic005","gene":"CYP2C19","phenotype":"Poor Metabolizer","drug":"omeprazole",
     "recommendation":"Standard dose may be sufficient or increase","evidence":"Strong",
     "text":"CYP2C19 Poor Metabolizers have impaired omeprazole metabolism leading to higher drug exposure. This is actually beneficial for acid suppression. Standard doses are generally sufficient or may even require reduction for extended therapy to avoid adverse effects."},
    {"id":"cpic006","gene":"CYP2C9","phenotype":"Poor Metabolizer","drug":"warfarin",
     "recommendation":"Reduce starting dose 50-75%","evidence":"Strong",
     "text":"CYP2C9 Poor Metabolizers have markedly reduced warfarin clearance. Starting doses must be reduced by 50-75% compared to normal metabolizers. High risk of over-anticoagulation and bleeding with standard doses. Frequent INR monitoring required during initiation. Use CPIC warfarin dosing algorithm combining CYP2C9 and VKORC1 genotype."},
    {"id":"cpic007","gene":"VKORC1","phenotype":"-1639G>A AA genotype","drug":"warfarin",
     "recommendation":"Significantly reduce dose","evidence":"Strong",
     "text":"VKORC1 -1639A variant reduces VKORC1 expression, decreasing warfarin dose requirement. AA homozygotes require approximately 40-50% lower warfarin doses than GG homozygotes. Must be combined with CYP2C9 genotype for accurate dose prediction using the CPIC warfarin dosing algorithm."},
    {"id":"cpic008","gene":"TPMT","phenotype":"Poor Metabolizer","drug":"azathioprine",
     "recommendation":"Use 10% of standard dose OR choose alternative","evidence":"Strong",
     "text":"TPMT Poor Metabolizers accumulate toxic thioguanine nucleotides with standard azathioprine doses. Risk of severe, life-threatening myelosuppression. CPIC recommends 10-fold dose reduction or use of non-thiopurine alternatives. FDA-approved label includes TPMT testing recommendation."},
    {"id":"cpic009","gene":"DPYD","phenotype":"Poor Metabolizer","drug":"fluorouracil",
     "recommendation":"AVOID or reduce dose 50%","evidence":"Strong",
     "text":"DPYD encodes dihydropyrimidine dehydrogenase which catabolizes 5-fluorouracil and capecitabine. DPYD Poor Metabolizers are at high risk of severe, potentially fatal fluoropyrimidine toxicity including neutropenia, mucositis, and neurotoxicity. Reduce dose by 50% or avoid. DPYD genotyping before chemotherapy is recommended."},
    {"id":"cpic010","gene":"CYP2D6","phenotype":"Poor Metabolizer","drug":"amitriptyline",
     "recommendation":"Reduce dose 50% or use alternative","evidence":"Strong",
     "text":"Amitriptyline and nortriptyline are primarily metabolized by CYP2D6. Poor Metabolizers have 2-3x increased plasma concentrations at standard doses, increasing risk of QTc prolongation, anticholinergic effects, and arrhythmia. CPIC recommends 50% dose reduction or switching to a non-CYP2D6-metabolized antidepressant."},
    {"id":"cpic011","gene":"HLA-B","phenotype":"57:01 carrier","drug":"abacavir",
     "recommendation":"CONTRAINDICATED","evidence":"Strong",
     "text":"HLA-B*57:01 allele is strongly associated with abacavir hypersensitivity syndrome — a severe, potentially fatal immune-mediated reaction. FDA Black Box Warning. Prospective HLA-B*57:01 screening reduces hypersensitivity incidence to near zero. CPIC recommends testing BEFORE initiating abacavir. Use alternative antiretroviral if positive."},
    {"id":"cpic012","gene":"SLCO1B1","phenotype":"Decreased Function","drug":"simvastatin",
     "recommendation":"Use lower dose or switch to pravastatin/rosuvastatin","evidence":"Strong",
     "text":"SLCO1B1 *5 variant reduces OATP1B1 hepatic transporter function, increasing simvastatin acid plasma exposure 2-3x. Associated with significantly increased risk of simvastatin-induced myopathy and rhabdomyolysis. CPIC recommends simvastatin 20mg maximum OR switch to pravastatin or rosuvastatin which are less affected by SLCO1B1."},
    {"id":"cpic013","gene":"G6PD","phenotype":"Deficient","drug":"rasburicase",
     "recommendation":"CONTRAINDICATED","evidence":"Strong",
     "text":"Rasburicase is absolutely contraindicated in G6PD-deficient patients. Causes severe hemolytic anemia due to hydrogen peroxide generation. FDA Black Box Warning. Screen all patients for G6PD deficiency before rasburicase administration. Use allopurinol as alternative for hyperuricemia management."},
    {"id":"cpic014","gene":"CYP2C19","phenotype":"Ultrarapid Metabolizer","drug":"escitalopram",
     "recommendation":"Consider higher starting dose","evidence":"Moderate",
     "text":"CYP2C19 Ultrarapid Metabolizers have increased escitalopram metabolism, leading to lower plasma concentrations at standard doses. Consider selecting an antidepressant not primarily metabolized by CYP2C19, or use a higher starting dose with therapeutic drug monitoring."},
    {"id":"cpic015","gene":"UGT1A1","phenotype":"Poor Metabolizer","drug":"irinotecan",
     "recommendation":"Reduce starting dose","evidence":"Strong",
     "text":"UGT1A1*28 homozygotes (TA7/TA7) have reduced UGT1A1 activity, impairing irinotecan glucuronidation. Results in increased SN-38 (active metabolite) exposure and risk of severe neutropenia and diarrhea. FDA label recommends dose reduction. CPIC recommends reducing starting dose by one dose level."},
]

# ─────────────────────────────────────────────────────────────────────────────
# VECTOR STORE — build or load ChromaDB
# ─────────────────────────────────────────────────────────────────────────────

_embed_model  = None
_chroma_client = None
_clinvar_col   = None
_cpic_col      = None


def _get_embedder():
    global _embed_model
    if _embed_model is None and SBERT_OK:
        _embed_model = SentenceTransformer(EMBED_MODEL)
    return _embed_model


def _get_chroma():
    global _chroma_client, _clinvar_col, _cpic_col
    if _chroma_client is not None:
        return _clinvar_col, _cpic_col

    if not CHROMA_OK or not SBERT_OK:
        return None, None

    _chroma_client = chromadb.PersistentClient(
        path=str(CHROMA_DIR),
        settings=Settings(anonymized_telemetry=False)
    )
    emb = _get_embedder()
    if emb is None:
        return None, None

    # ClinVar collection
    try:
        _clinvar_col = _chroma_client.get_collection("clinvar")
    except Exception:
        _clinvar_col = _chroma_client.create_collection("clinvar")
        docs  = [d["text"] for d in CLINVAR_SEED]
        ids   = [d["id"]   for d in CLINVAR_SEED]
        metas = [{k: v for k, v in d.items() if k != "text"} for d in CLINVAR_SEED]
        embs  = emb.encode(docs).tolist()
        _clinvar_col.add(documents=docs, ids=ids, metadatas=metas, embeddings=embs)

    # CPIC collection
    try:
        _cpic_col = _chroma_client.get_collection("cpic")
    except Exception:
        _cpic_col = _chroma_client.create_collection("cpic")
        docs  = [d["text"] for d in CPIC_SEED]
        ids   = [d["id"]   for d in CPIC_SEED]
        metas = [{k: v for k, v in d.items() if k != "text"} for d in CPIC_SEED]
        embs  = emb.encode(docs).tolist()
        _cpic_col.add(documents=docs, ids=ids, metadatas=metas, embeddings=embs)

    return _clinvar_col, _cpic_col


def retrieve_clinvar(gene: str, variant: str = "", n: int = 3) -> list:
    clinvar_col, _ = _get_chroma()
    if clinvar_col is None:
        return [d["text"] for d in CLINVAR_SEED if d["gene"].upper() == gene.upper()][:n]
    emb   = _get_embedder()
    query = f"{gene} {variant} pathogenic variant clinical significance"
    qvec  = emb.encode([query]).tolist()
    res   = clinvar_col.query(query_embeddings=qvec, n_results=min(n, len(CLINVAR_SEED)))
    return res["documents"][0] if res["documents"] else []


def retrieve_cpic(gene: str, phenotype: str = "", drug: str = "", n: int = 3) -> list:
    _, cpic_col = _get_chroma()
    if cpic_col is None:
        return [d["text"] for d in CPIC_SEED if d["gene"].upper() == gene.upper()][:n]
    emb   = _get_embedder()
    query = f"{gene} {phenotype} {drug} pharmacogenomics dose recommendation"
    qvec  = emb.encode([query]).tolist()
    res   = cpic_col.query(query_embeddings=qvec, n_results=min(n, len(CPIC_SEED)))
    return res["documents"][0] if res["documents"] else []


# ─────────────────────────────────────────────────────────────────────────────
# LOCAL LLM — Ollama
# ─────────────────────────────────────────────────────────────────────────────

def _ollama_available() -> bool:
    if not OLLAMA_OK:
        return False
    try:
        result = _ollama.list()
        # Handle both old API (object with .models) and new API (dict)
        if isinstance(result, dict):
            model_list = result.get("models", [])
            names = [m.get("model", m.get("name", "")) for m in model_list]
        else:
            names = [m.model for m in result.models]
        return any(OLLAMA_MODEL.split(":")[0] in n for n in names)
    except Exception:
        return False


def _llm_generate(prompt: str, max_tokens: int = 400) -> str:
    if not _ollama_available():
        return None
    try:
        resp = _ollama.generate(
            model=OLLAMA_MODEL,
            prompt=prompt,
            options={"num_predict": max_tokens, "temperature": 0.3, "top_p": 0.9}
        )
        return resp.response.strip()
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# RULE-BASED FALLBACK (always works, zero dependencies)
# ─────────────────────────────────────────────────────────────────────────────

def _rule_based_variant_text(gene, variant, acmg_class, consequence, condition=""):
    HIGH_RISK_GENES = {"BRCA1","BRCA2","TP53","MLH1","MSH2","MSH6","PALB2","ATM","CHEK2","PTEN","CDH1","APC"}
    PGX_GENES       = {"CYP2D6","CYP2C19","CYP2C9","DPYD","TPMT","UGT1A1","SLCO1B1","G6PD","VKORC1","HLA-B"}

    severity_map = {
        "Pathogenic":             "This variant has strong clinical evidence of pathogenicity",
        "Likely Pathogenic":      "This variant is likely pathogenic based on current evidence",
        "Uncertain Significance": "This variant is of uncertain clinical significance",
        "Likely Benign":          "This variant is likely benign based on current evidence",
        "Benign":                 "This variant is classified as benign",
    }
    severity = severity_map.get(acmg_class, "This variant has been classified")

    context = ""
    if gene in HIGH_RISK_GENES:
        context = (f"{gene} is a high-penetrance cancer predisposition gene. "
                   f"Pathogenic variants are associated with significantly elevated lifetime cancer risk "
                   f"and require specialist oncogenetics referral.")
    elif gene in PGX_GENES:
        context = (f"{gene} is a pharmacogenomically relevant gene. "
                   f"Variants affect drug metabolism and may require medication dose adjustments.")

    rec_map = {
        "Pathogenic":             "Clinical correlation and genetic counselling are strongly recommended. Cascade testing of first-degree relatives should be considered.",
        "Likely Pathogenic":      "Clinical correlation and genetic counselling are recommended. Variant reclassification may occur as evidence accumulates.",
        "Uncertain Significance": "Clinical management should not be altered solely based on this VUS. Periodic reclassification review is recommended.",
        "Likely Benign":          "No immediate clinical action required. Standard screening guidelines apply.",
        "Benign":                 "No clinical action required based on this variant.",
    }
    rec = rec_map.get(acmg_class, "Clinical correlation recommended.")

    para1 = f"{severity} ({acmg_class}). {context}".strip()
    para2 = f"Molecular consequence: {consequence}. {rec}".strip()
    return para1, para2


def _rule_based_pgx_text(gene, diplotype, phenotype, drugs):
    drug_list = ", ".join(drugs[:4]) if drugs else "affected medications"
    para1 = (f"The patient carries the {gene} genotype {diplotype}, resulting in a "
             f"{phenotype} phenotype. This affects the metabolism of {drug_list}.")

    context = ""
    for entry in CPIC_SEED:
        if entry["gene"] == gene and entry["phenotype"].lower() in phenotype.lower():
            context = f"CPIC Recommendation: {entry['recommendation']}. {entry['text'][:250]}"
            break
    if not context:
        context = (f"Consult CPIC guidelines at cpicpgx.org for specific dosing recommendations. "
                   f"Standard dose protocols apply unless genotype-guided adjustment is indicated.")
    return para1, context


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def interpret_variant(gene, variant, acmg_class, consequence, condition="", use_llm=True):
    """
    Generate a clinical interpretation for a single variant.
    Returns: {paragraph1, paragraph2, source ('llm'|'rag'|'rule'), context}
    """
    context_docs = retrieve_clinvar(gene, variant, n=2)
    context_text = "\n".join(context_docs[:2]) if context_docs else ""

    if use_llm and _ollama_available() and context_text:
        prompt = (
            f"You are a clinical genomics expert writing a report for a physician.\n\n"
            f"VARIANT INFORMATION:\n"
            f"Gene: {gene}\nVariant: {variant}\nACMG Classification: {acmg_class}\n"
            f"Molecular Consequence: {consequence}\n"
            f"{('Associated Condition: ' + condition) if condition else ''}\n\n"
            f"RELEVANT KNOWLEDGE BASE:\n{context_text}\n\n"
            f"Write a concise 2-paragraph clinical interpretation:\n"
            f"- Paragraph 1: Clinical significance and disease association\n"
            f"- Paragraph 2: Molecular mechanism and management recommendation\n"
            f"Be specific, clinical, and evidence-based. Plain paragraphs only, no bullet points."
        )
        llm_text = _llm_generate(prompt, max_tokens=350)
        if llm_text:
            paras = [p.strip() for p in llm_text.split("\n\n") if p.strip()]
            p1 = paras[0] if paras else llm_text[:300]
            p2 = paras[1] if len(paras) > 1 else ""
            return {"paragraph1": p1, "paragraph2": p2, "source": "llm", "context": context_text}

    if context_text:
        p1, p2 = _rule_based_variant_text(gene, variant, acmg_class, consequence, condition)
        supporting = context_docs[0][:200] + "..." if context_docs else ""
        return {"paragraph1": p1, "paragraph2": p2 + f" {supporting}",
                "source": "rag", "context": context_text}

    p1, p2 = _rule_based_variant_text(gene, variant, acmg_class, consequence, condition)
    return {"paragraph1": p1, "paragraph2": p2, "source": "rule", "context": ""}


def explain_pgx(gene, diplotype, phenotype, drugs, use_llm=True):
    """
    Generate a clinical PGx drug safety summary.
    Returns: {paragraph1, paragraph2, recommendations, source}
    """
    context_docs = retrieve_cpic(gene, phenotype, drugs[0] if drugs else "", n=3)
    context_text = "\n".join(context_docs[:3]) if context_docs else ""
    drug_list    = ", ".join(drugs[:5]) if drugs else "relevant medications"

    if use_llm and _ollama_available() and context_text:
        prompt = (
            f"You are a clinical pharmacist writing a pharmacogenomics report.\n\n"
            f"PATIENT PGX:\nGene: {gene}\nDiplotype: {diplotype}\nPhenotype: {phenotype}\n"
            f"Affected Medications: {drug_list}\n\n"
            f"CPIC GUIDELINES:\n{context_text}\n\n"
            f"Write a concise 2-paragraph clinical PGx summary:\n"
            f"- Paragraph 1: What this genotype means for drug metabolism\n"
            f"- Paragraph 2: Specific actionable recommendations for each medication\n"
            f"Be precise and actionable. Use medication names. No bullet points."
        )
        llm_text = _llm_generate(prompt, max_tokens=300)
        if llm_text:
            paras = [p.strip() for p in llm_text.split("\n\n") if p.strip()]
            p1 = paras[0] if paras else llm_text[:300]
            p2 = paras[1] if len(paras) > 1 else ""
            recs = [f"{e['drug'].upper()}: {e['recommendation']}"
                    for e in CPIC_SEED
                    if e["gene"] == gene and e["phenotype"].lower() in phenotype.lower()]
            return {"paragraph1": p1, "paragraph2": p2, "recommendations": recs, "source": "llm"}

    p1, p2 = _rule_based_pgx_text(gene, diplotype, phenotype, drugs)
    recs = [f"{e['drug'].upper()}: {e['recommendation']}"
            for e in CPIC_SEED
            if e["gene"] == gene and e["phenotype"].lower() in phenotype.lower()]
    return {"paragraph1": p1, "paragraph2": p2, "recommendations": recs, "source": "rule"}


def batch_interpret_top_variants(acmg_rows, max_variants=5):
    """
    Interpret the top N P/LP/VUS variants from ACMG results.
    acmg_rows: list of dicts with keys: gene, variant/hgvs_c, classification, consequence/so_term
    """
    priority = ["Pathogenic", "Likely Pathogenic", "Uncertain Significance"]
    sorted_rows = sorted(
        acmg_rows,
        key=lambda r: priority.index(r.get("classification", ""))
        if r.get("classification", "") in priority else 99
    )
    results = []
    for row in sorted_rows[:max_variants]:
        interp = interpret_variant(
            gene        = row.get("gene", "Unknown"),
            variant     = row.get("variant", row.get("hgvs_c", "")),
            acmg_class  = row.get("classification", "Uncertain Significance"),
            consequence = row.get("consequence", row.get("so_term", "")),
            condition   = row.get("condition", ""),
        )
        interp["gene"]       = row.get("gene", "")
        interp["variant"]    = row.get("variant", row.get("hgvs_c", ""))
        interp["acmg_class"] = row.get("classification", "")
        results.append(interp)
    return results


def ai_status():
    """Return current AI engine status for UI display."""
    return {
        "chromadb":    CHROMA_OK,
        "embeddings":  SBERT_OK,
        "ollama":      OLLAMA_OK,
        "llm_ready":   _ollama_available(),
        "model":       OLLAMA_MODEL,
        "mode":        "llm" if _ollama_available() else ("rag" if (CHROMA_OK and SBERT_OK) else "rule"),
        "clinvar_docs": len(CLINVAR_SEED),
        "cpic_docs":    len(CPIC_SEED),
    }
