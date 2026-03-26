"""
OncoPanther-AI — First-Run Setup Progress Page
Shows download progress in browser during initial ref data setup.
"""
import streamlit as st
import os, time
from pathlib import Path

REFS_DIR = Path(os.environ.get("REFS_DIR", "/refs"))
STATUS_FILE = REFS_DIR / ".setup_complete"
SETUP_LOG   = REFS_DIR / "setup.log"
SETUP_STATUS= REFS_DIR / ".setup_status"

st.set_page_config(
    page_title="OncoPanther-AI Setup",
    page_icon="🧬",
    layout="centered"
)

st.markdown("""
<style>
    .main { background: #0f1923; }
    .stApp { background: #0f1923; }
    h1, h2, h3, p, div { color: white !important; }
    .progress-bar { background: #1B4F8A; border-radius: 8px; padding: 20px; margin: 10px 0; }
    .step-done { color: #27AE60 !important; font-weight: bold; }
    .step-running { color: #F39C12 !important; font-weight: bold; }
    .step-pending { color: #7f8c8d !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div style="text-align:center; padding: 30px 0;">
    <div style="font-size:48px; font-weight:900; color:#E74C3C;">
        Onco<span style="color:#E74C3C">P</span><span style="color:white">anther-AI</span>
    </div>
    <div style="font-size:18px; color:#aaa; margin-top:8px;">
        First-Time Setup — Downloading Reference Data
    </div>
</div>
""", unsafe_allow_html=True)

st.info("⏳ **This only happens ONCE.** After setup, OncoPanther starts instantly every time.")

st.markdown("---")

# Steps
steps = [
    ("GRCh38 Reference Genome", "3.1 GB", "GRCh38/GRCh38_full_analysis_set.fna"),
    ("BWA-MEM2 Index", "8 GB", "GRCh38/GRCh38_full_analysis_set.fna.bwt.2bit.64"),
    ("VEP GRCh38 Cache", "25 GB", "vep_cache/homo_sapiens"),
    ("ClinVar VCF", "1 GB", "clinvar/clinvar.vcf.gz"),
    ("GATK Dictionary", "10 MB", "GRCh38/GRCh38_full_analysis_set.dict"),
]

st.markdown("### Setup Progress")

placeholder = st.empty()

while not STATUS_FILE.exists():
    with placeholder.container():
        for name, size, check_path in steps:
            full_path = REFS_DIR / check_path
            if full_path.exists():
                st.markdown(f'<div class="step-done">✅ {name} ({size}) — Done</div>', unsafe_allow_html=True)
            else:
                # Check current status
                current = ""
                if SETUP_STATUS.exists():
                    current = SETUP_STATUS.read_text().strip()
                if name.split()[0].lower() in current.lower():
                    st.markdown(f'<div class="step-running">⏳ {name} ({size}) — Downloading...</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="step-pending">🔲 {name} ({size}) — Waiting</div>', unsafe_allow_html=True)

        st.markdown("---")

        # Show log tail
        if SETUP_LOG.exists():
            log_lines = SETUP_LOG.read_text().split("\n")[-8:]
            st.markdown("**Live Log:**")
            st.code("\n".join(log_lines), language=None)

        # Disk space
        try:
            import shutil
            total, used, free = shutil.disk_usage(str(REFS_DIR))
            st.metric("Disk Free", f"{free // (1024**3)} GB")
        except:
            pass

    time.sleep(10)
    st.rerun()

# Setup complete
st.success("✅ Setup Complete! OncoPanther-AI is starting...")
st.balloons()
st.markdown("### 🚀 Redirecting to OncoPanther...")
st.markdown("Refresh your browser in 10 seconds → Full pipeline ready!")
