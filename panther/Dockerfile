# ═══════════════════════════════════════════════════════════════════════════
# OncoPanther-AI Clinical Genomics Pipeline
# Docker Image — Full Stack (Pipeline + Streamlit App)
#
# Usage:
#   docker build -t abpeele/oncopanther-ai:latest .
#   docker run -p 8501:8501 \
#     -v /path/to/refs:/refs \
#     -v /path/to/data:/data \
#     abpeele/oncopanther-ai:latest
# ═══════════════════════════════════════════════════════════════════════════

FROM ubuntu:22.04
LABEL maintainer="OncoPanther Team"
LABEL version="2.0.0"
LABEL description="OncoPanther-AI: End-to-end clinical genomics pipeline (FASTQ → VCF → PGx → PDF) + Offline AI interpretation (RAG + LLM)"

# ── Prevent interactive prompts ─────────────────────────────────────────────
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Kolkata

# ── System dependencies ──────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y \
    wget curl git unzip bzip2 ca-certificates \
    build-essential libssl-dev libffi-dev \
    openjdk-17-jdk-headless \
    perl libdbi-perl libdbd-mysql-perl \
    zlib1g-dev libbz2-dev liblzma-dev \
    libcurl4-openssl-dev \
    fonts-dejavu-core \
    procps htop \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── Java home ────────────────────────────────────────────────────────────────
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH=$JAVA_HOME/bin:$PATH

# ── Miniforge (conda-forge by default, no Anaconda TOS) ──────────────────────
RUN curl -fsSL --retry 5 --retry-connrefused --retry-delay 5 \
    https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh \
    -o /tmp/miniforge.sh && \
    bash /tmp/miniforge.sh -b -p /opt/conda && \
    rm /tmp/miniforge.sh

ENV PATH=/opt/conda/bin:$PATH
ENV CONDA_AUTO_UPDATE_CONDA=false
ENV MAMBA_NO_BANNER=1

# ── Configure channels (bioconda + conda-forge, strict priority) ──────────────
RUN conda config --add channels bioconda && \
    conda config --set channel_priority strict && \
    mamba clean -afy

# ── Install core bioinformatics tools via mamba ────────────────────────────────
RUN mamba install -y -n base \
    python=3.12 \
    nextflow=24.04.4 \
    fastqc=0.12.1 \
    multiqc=1.27 \
    samtools=1.21 \
    bcftools=1.21 \
    gatk4=4.4.0.0 \
    picard=3.2.0 \
    bwa-mem2=2.2.1 \
    trimmomatic=0.39 \
    fastp=0.23.2 \
    deeptools=3.5.5 \
    qualimap=2.3 \
    && mamba clean -afy

# ── Install VEP ──────────────────────────────────────────────────────────────
RUN mamba install -y -n base ensembl-vep=114.2 && mamba clean -afy

# ── Install PharmCAT ─────────────────────────────────────────────────────────
RUN mamba install -y -n base pharmcat3=3.1.1 && mamba clean -afy

# ── Install Python packages (Streamlit + pipeline) ───────────────────────────
RUN pip install --no-cache-dir \
    streamlit==1.32.0 \
    reportlab==4.1.0 \
    pandas==2.2.0 \
    numpy==1.26.4 \
    matplotlib==3.8.3 \
    seaborn==0.13.2 \
    plotly==5.19.0 \
    kaleido==0.2.1 \
    pyyaml==6.0.1 \
    fastapi==0.110.0 \
    uvicorn==0.27.1 \
    python-multipart==0.0.9 \
    biopython==1.83 \
    pysam==0.22.0 \
    tqdm==4.66.2 \
    requests==2.31.0 \
    jinja2==3.1.3

# ── AI / RAG packages (separate layer — different version constraints) ────────
RUN pip install --no-cache-dir \
    chromadb==1.5.5 \
    sentence-transformers==3.0.1 \
    langchain==0.3.0 \
    langchain-community==0.3.0 \
    ollama==0.3.3

# ── Install Ollama (local LLM runner, CPU + GPU) ─────────────────────────────
RUN apt-get update && apt-get install -y zstd && apt-get clean && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://ollama.com/install.sh | sh

# ── Pre-download llama3.2:3b model (2 GB — baked into image, zero internet needed) ──
# Start Ollama server, pull model, stop server
RUN ollama serve & \
    sleep 8 && \
    ollama pull llama3.2:3b && \
    pkill ollama || true

ENV OLLAMA_HOST=0.0.0.0:11434
ENV ONCOPANTHER_LLM=llama3.2:3b

# ── Install Cyrius (CYP2D6 caller) ───────────────────────────────────────────
RUN git clone https://github.com/Illumina/Cyrius.git /opt/cyrius && \
    pip install --no-cache-dir -r /opt/cyrius/requirements.txt
ENV PATH=/opt/cyrius:$PATH

# ── Copy pipeline code ───────────────────────────────────────────────────────
WORKDIR /app
COPY . /app/panther/

# ── Set up Nextflow config ───────────────────────────────────────────────────
ENV NXF_HOME=/app/.nextflow
ENV NXF_CACHE_DIR=/app/.nextflow/cache
RUN mkdir -p /app/.nextflow/cache

# ── Mount points for reference data ──────────────────────────────────────────
# /refs/  → Docker VOLUME (persists across runs — downloaded ONCE on first run)
#   /refs/GRCh38/          → GRCh38 reference + BWA index   (12 GB)
#   /refs/vep_cache/       → VEP GRCh38 cache               (25 GB)
#   /refs/clinvar/         → ClinVar VCF                     (1 GB)
#   /refs/.setup_complete  → Flag file: exists = refs ready
# /data/  → Patient data (mounted per-run)
#   /data/input/           → Patient FASTQs / VCFs
#   /data/output/          → Pipeline results + PDFs
RUN mkdir -p /refs/GRCh38 /refs/vep_cache /refs/clinvar \
             /data/input /data/output

# Declare volume — Docker will persist /refs across container restarts
VOLUME ["/refs", "/data"]

# ── Streamlit config ─────────────────────────────────────────────────────────
RUN mkdir -p /root/.streamlit
RUN echo '\
[server]\n\
port = 8501\n\
address = "0.0.0.0"\n\
headless = true\n\
maxUploadSize = 2048\n\
enableCORS = false\n\
enableXsrfProtection = false\n\
\n\
[browser]\n\
gatherUsageStats = false\n\
' > /root/.streamlit/config.toml

# ── Entrypoint script ────────────────────────────────────────────────────────
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# ── Expose ports ─────────────────────────────────────────────────────────────
# 8501 = Streamlit app
# 8000 = FastAPI REST API
EXPOSE 8501 8000

# ── Health check ─────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
