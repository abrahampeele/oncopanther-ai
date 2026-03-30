# OncoPanther-AI

[![Nextflow](https://img.shields.io/badge/nextflow%20DSL2-%E2%89%A524.10.5-23aa62.svg)](https://www.nextflow.io/)
[![run with docker](https://img.shields.io/badge/run%20with-docker-0db7ed?labelColor=000000&logo=docker)](https://www.docker.com/)
[![run with singularity](https://img.shields.io/badge/run%20with-singularity-1d355c.svg?labelColor=000000)](https://sylabs.io/docs/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.placeholder.svg)](https://doi.org/10.5281/zenodo.placeholder)

**An offline, privacy-preserving Nextflow pipeline for integrated germline variant classification, pharmacogenomics, and AI-generated clinical genomic narratives.**

> Manuscript submitted to *Briefings in Bioinformatics* (Application Note, 2026)

---

## Overview

OncoPanther-AI performs end-to-end clinical WGS interpretation from a single command, producing:

| Module | Output |
|--------|--------|
| **(A) Alignment & QC** | BWA-MEM2 BAM, FastQC/QualiMap reports |
| **(B) Scatter Variant Calling** | Merged gVCF (25× parallel HaplotypeCaller, 2.9× speedup) |
| **(C) ACMG/AMP Classification** | Annotated VCF with 5-tier pathogenicity + VEP/CADD/SpliceAI |
| **(D) Pharmacogenomics** | PharmCAT diplotype report for 24 CPIC tier 1/2 genes |
| **(E) Offline AI Narrative** | Patient-specific clinical summaries via LLaMA 3.2 3B + ChromaDB RAG |

**Key feature:** All processing is local. No patient data is transmitted to external APIs or cloud services.

---

## Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| OS | Linux x86_64 / WSL2 | Ubuntu 22.04 |
| RAM | 16 GB | 32 GB |
| CPU cores | 8 | 16+ |
| Storage | 200 GB | 500 GB |
| Docker | ≥ 20.10 | latest |
| Nextflow | ≥ 24.04 | 24.10+ |

GPU optional (AI narrative engine runs on CPU).

---

## Quick Start

```bash
# 1. Pull the Docker image
docker pull abrahampeele/oncopanther-ai:v1.3.0

# 2. Run full pipeline (BAM → report)
nextflow run abrahampeele/oncopanther-ai \
  --input     samples.csv \
  --reference /path/to/GRCh38.fna \
  --outdir    ./results \
  -profile    docker

# 3. Or run stepmode (e.g. variant calling only)
nextflow run main.nf \
  --stepmode  varcall \
  --tovarcall samples.csv \
  --reference /path/to/GRCh38.fna \
  --outdir    ./results \
  -profile    docker
```

`samples.csv` format:
```csv
sample_id,bam,bai
PT-001,/data/PT-001.bam,/data/PT-001.bam.bai
```

---

## GIAB Validation (v1.3.0)

Benchmarked against GIAB HG001 (NA12878) NISTv3.3.2, GRCh38, 5× WGS demo coverage:

| Type | Precision | Recall | F1 |
|------|-----------|--------|----|
| SNP | **0.9515** | 0.4011 | 0.5643 |
| INDEL | **0.8856** | 0.2224 | 0.3555 |

*Recall is depth-limited at 5× coverage. At clinical 30× WGS, GATK 4.4 achieves SNP F1 >0.998.*

Runtime benchmark (chr1, 16-core node):

| Method | Wall Time | Speedup |
|--------|-----------|---------|
| Standard GATK (1 thread) | 25 min 16 s | 1.0× |
| OncoPanther-AI scatter (4×) | 8 min 49 s | **2.9×** |

Projected whole-genome speedup: **5.3×** (25 chr parallel).

---

## Pipeline Modes

```
fullmode   — FASTQ → final report (alignment + all modules)
stepmode   — modular execution:
  qc         Quality control only
  align      Alignment only
  varcall    Variant calling (scatter GATK)
  annotate   ACMG annotation + VEP
  pgx        PharmCAT pharmacogenomics
  narrative  AI narrative generation
  validate   GIAB benchmarking (Module 11.0)
  benchmark  Runtime benchmark (Module 11.1)
```

---

## AI Narrative Engine

The offline RAG architecture:
1. **Knowledge base**: ClinVar summaries + OMIM descriptions + CPIC guidelines → ChromaDB vector DB
2. **Retrieval**: Top-5 chunks by cosine similarity (sentence-transformers `all-MiniLM-L6-v2`)
3. **Generation**: LLaMA 3.2 3B (4-bit quantized via Ollama) — CPU or GPU
4. **Review**: Streamlit dashboard for clinician editing before sign-out

All inference is local. No API keys required.

---

## Streamlit Dashboard

```bash
# Start the interactive report viewer
docker exec -it oncopanther streamlit run /app/panther/demo_app/app.py --server.port 8501

# Open: http://localhost:8501
# Tabs: Variant Review | PGx Report | AI Narratives | Narrative Evaluation
```

---

## Citation

If you use OncoPanther-AI, please cite:

```
[Author(s)]. OncoPanther-AI: An Offline, Privacy-Preserving Nextflow Pipeline for
Integrated Germline Variant Classification, Pharmacogenomics, and AI-Generated
Clinical Genomic Narratives. Briefings in Bioinformatics, 2026.
https://github.com/abrahampeele/oncopanther-ai
```

Or use [`CITATION.cff`](CITATION.cff) for automatic citation formatting.

---

## License

MIT — see [LICENSE](LICENSE).
