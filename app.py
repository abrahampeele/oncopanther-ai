import streamlit as st
import json
from datetime import datetime
from pathlib import Path

st.set_page_config(page_title="OncoPanther PGx Demo", page_icon="🧬", layout="wide")

st.title("🧬 OncoPanther AI - Pharmacogenomics Demo")
st.markdown("**AI-Powered Clinical Genomics Platform**")

# Sidebar
with st.sidebar:
    st.image("https://via.placeholder.com/300x100/1e3a8a/ffffff?text=OncoPanther+AI", use_container_width=True)
    st.markdown("### Demo Mode")
    st.info("This demo uses simulated genomic data for educational purposes.")

# Patient Information
st.header("📋 Patient Information")

col1, col2, col3 = st.columns(3)

with col1:
    patient_id = st.text_input("Patient ID", value="PGX-2026-001")
    age = st.number_input("Age", min_value=0, max_value=120, value=45)

with col2:
    patient_name = st.text_input("Patient Name", value="John Doe")
    gender = st.selectbox("Gender", ["Male", "Female", "Other"])

with col3:
    ethnicity = st.selectbox("Ethnicity", ["Caucasian", "African", "Asian", "Hispanic", "Other"])
    physician = st.text_input("Ordering Physician", value="Dr. Smith")

indication = st.text_area("Clinical Indication", value="Pre-treatment screening for chemotherapy")
medications = st.text_area("Current Medications", value="Warfarin 5mg daily, Clopidogrel 75mg")

# Simulated Variants
st.header("🧬 Detected PGx Variants (Demo Data)")

variants_data = [
    {"gene": "CYP2D6", "variant": "*4/*10", "phenotype": "Intermediate Metabolizer", "drugs": "Codeine, Tamoxifen, Metoprolol"},
    {"gene": "CYP2C19", "variant": "*2/*17", "phenotype": "Intermediate Metabolizer", "drugs": "Clopidogrel, Escitalopram"},
    {"gene": "SLCO1B1", "variant": "rs4149056", "phenotype": "Increased Statin Risk", "drugs": "Simvastatin, Atorvastatin"}
]

st.table(variants_data)

# Generate Report Button
if st.button("🚀 Generate AI-Powered Report", type="primary", use_container_width=True):
    with st.spinner("Analyzing genomic data with AI..."):
        import time
        time.sleep(2)  # Simulate processing
        
        st.success("✅ Report Generated Successfully!")
        
        # Display Summary
        st.subheader("📊 Executive Summary")
        st.info("Patient carries pharmacogenomic variants affecting drug metabolism in CYP2D6, CYP2C19, and SLCO1B1 genes. Current medications require careful monitoring and potential dose adjustment.")
        
        # Key Findings
        st.subheader("🔍 Key Findings")
        findings = [
            "CYP2C19 intermediate metabolizer: Clopidogrel may have reduced efficacy",
            "CYP2D6 intermediate metabolizer: Affects 25% of medications",
            "SLCO1B1 variant: Increased risk of statin-induced myopathy"
        ]
        
        for finding in findings:
            st.markdown(f"✓ {finding}")
        
        # Download Report
        st.subheader("📥 Download Report")
        
        report_html = f"""
        <!DOCTYPE html>
        <html>
        <head><title>PGx Report - {patient_id}</title>
        <style>
        body {{ font-family: Arial; margin: 40px; line-height: 1.6; }}
        h1 {{ color: #1e3a8a; text-align: center; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background: #1e3a8a; color: white; }}
        </style></head>
        <body>
        <h1>PHARMACOGENOMIC TEST REPORT</h1>
        <p style="text-align:center"><strong>OncoPanther AI</strong> | Generated: {datetime.now().strftime('%Y-%m-%d')}</p>
        
        <h2>PATIENT INFORMATION</h2>
        <table>
        <tr><td><strong>ID</strong></td><td>{patient_id}</td></tr>
        <tr><td><strong>Name</strong></td><td>{patient_name}</td></tr>
        <tr><td><strong>Age/Gender</strong></td><td>{age} / {gender}</td></tr>
        </table>
        
        <h2>DETECTED VARIANTS</h2>
        <table>
        <thead><tr><th>Gene</th><th>Variant</th><th>Phenotype</th><th>Affected Drugs</th></tr></thead>
        <tbody>
        {''.join([f"<tr><td>{v['gene']}</td><td>{v['variant']}</td><td>{v['phenotype']}</td><td>{v['drugs']}</td></tr>" for v in variants_data])}
        </tbody>
        </table>
        
        <h2>KEY FINDINGS</h2>
        <ul>
        {''.join([f"<li>{f}</li>" for f in findings])}
        </ul>
        
        <p style="text-align:center; margin-top:50px; border-top:1px solid #ccc; padding-top:20px;">
        <strong>OncoPanther AI</strong> - AI-Powered Virtual Molecular Tumor Board</p>
        </body></html>
        """
        
        st.download_button(
            label="📄 Download Report (HTML)",
            data=report_html,
            file_name=f"{patient_id}_PGx_Report.html",
            mime="text/html"
        )

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666;'>
    <p><strong>OncoPanther AI</strong> - Demo Version | For Educational Purposes</p>
    <p style='font-size: 0.8rem;'>Clinical decisions should be made by qualified healthcare professionals.</p>
</div>
""", unsafe_allow_html=True)
