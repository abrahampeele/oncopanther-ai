"""
OncoPanther-AI — FastAPI REST API
Endpoints for partner integration into hospital / LIMS systems

Usage:
    uvicorn demo_app.api:app --host 0.0.0.0 --port 8000 --reload
    Docs: http://localhost:8000/docs
"""

import os, json, uuid, shutil, subprocess, threading
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── App setup ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="OncoPanther-AI REST API",
    description=(
        "Clinical Genomics Pipeline API\n\n"
        "Convert raw genomic data (FASTQ/VCF) into clinically actionable "
        "insights (ACMG + CPIC) via automated pipeline.\n\n"
        "**Partner integration endpoint for LIMS / Hospital Systems**"
    ),
    version="1.0.0",
    contact={"name": "OncoPanther Team"},
    license_info={"name": "Research Use Only"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PANTHER_DIR = Path(__file__).parent.parent
OUTDIR      = PANTHER_DIR / "outdir"
UPLOAD_DIR  = PANTHER_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# In-memory job tracker (replace with DB for production)
JOBS: dict = {}

# ── Models ───────────────────────────────────────────────────────────────────
class JobStatus(BaseModel):
    job_id: str
    status: str          # queued | running | completed | failed
    patient_id: str
    started_at: str
    completed_at: Optional[str] = None
    pgx_results: Optional[dict] = None
    acmg_results: Optional[list] = None
    report_url: Optional[str] = None
    error: Optional[str] = None

class PgxAnalysisRequest(BaseModel):
    patient_id: str
    guidelines: str = "CPIC"
    physician: Optional[str] = None
    diagnosis: Optional[str] = None

# ── Health ───────────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
def root():
    return {
        "service": "OncoPanther-AI REST API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "timestamp": datetime.utcnow().isoformat(),
    }

@app.get("/health", tags=["Health"])
def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

# ── VCF → PGx Analysis ───────────────────────────────────────────────────────
@app.post("/api/v1/analyze/vcf", tags=["Analysis"])
async def analyze_vcf(
    background_tasks: BackgroundTasks,
    vcf_file: UploadFile = File(..., description="VCF or VCF.GZ file"),
    patient_id: str = Form(..., description="Unique patient/sample identifier"),
    guidelines: str = Form("CPIC", description="CPIC | DPWG | FDA"),
    physician: Optional[str] = Form(None),
    diagnosis: Optional[str] = Form(None),
):
    """
    Upload a VCF file → run PharmCAT PGx analysis → return star alleles + drug recommendations.

    **Typical use:** Pre-called variants from hospital LIMS → get PGx report.
    **Time:** 5–10 minutes
    """
    job_id = str(uuid.uuid4())[:8].upper()
    upload_path = UPLOAD_DIR / f"{job_id}_{patient_id}.vcf.gz"

    # Save uploaded file
    with open(upload_path, "wb") as f:
        f.write(await vcf_file.read())

    JOBS[job_id] = {
        "job_id": job_id, "status": "queued",
        "patient_id": patient_id, "started_at": datetime.utcnow().isoformat(),
        "completed_at": None, "pgx_results": None,
        "acmg_results": None, "report_url": None, "error": None,
    }

    background_tasks.add_task(
        _run_pgx_pipeline, job_id, patient_id,
        str(upload_path), guidelines, physician, diagnosis
    )

    return JSONResponse({"job_id": job_id, "status": "queued",
                         "message": f"PGx analysis started. Poll /api/v1/jobs/{job_id} for status."})


# ── FASTQ → Full Pipeline ────────────────────────────────────────────────────
@app.post("/api/v1/analyze/fastq", tags=["Analysis"])
async def analyze_fastq(
    background_tasks: BackgroundTasks,
    r1_file: UploadFile = File(..., description="R1 FASTQ.GZ"),
    r2_file: UploadFile = File(..., description="R2 FASTQ.GZ (paired-end)"),
    patient_id: str = Form(...),
    guidelines: str = Form("CPIC"),
    physician: Optional[str] = Form(None),
    diagnosis: Optional[str] = Form(None),
):
    """
    Upload FASTQ files → full pipeline (alignment + variant calling + PGx).

    **Time:** 1–4 hours depending on coverage.
    """
    job_id = str(uuid.uuid4())[:8].upper()
    r1_path = UPLOAD_DIR / f"{job_id}_{patient_id}_R1.fastq.gz"
    r2_path = UPLOAD_DIR / f"{job_id}_{patient_id}_R2.fastq.gz"

    with open(r1_path, "wb") as f: f.write(await r1_file.read())
    with open(r2_path, "wb") as f: f.write(await r2_file.read())

    JOBS[job_id] = {
        "job_id": job_id, "status": "queued",
        "patient_id": patient_id, "started_at": datetime.utcnow().isoformat(),
        "completed_at": None, "pgx_results": None,
        "acmg_results": None, "report_url": None, "error": None,
    }

    background_tasks.add_task(
        _run_full_pipeline, job_id, patient_id,
        str(r1_path), str(r2_path), guidelines
    )

    return JSONResponse({"job_id": job_id, "status": "queued",
                         "message": f"Full pipeline started. Poll /api/v1/jobs/{job_id} for status."})


# ── Job Status ───────────────────────────────────────────────────────────────
@app.get("/api/v1/jobs/{job_id}", tags=["Jobs"])
def get_job_status(job_id: str):
    """Poll job status and get results when complete."""
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return JOBS[job_id]

@app.get("/api/v1/jobs", tags=["Jobs"])
def list_jobs():
    """List all jobs."""
    return {"jobs": list(JOBS.values()), "total": len(JOBS)}


# ── Download Report ──────────────────────────────────────────────────────────
@app.get("/api/v1/jobs/{job_id}/report", tags=["Reports"])
def download_report(job_id: str):
    """Download the clinical PDF report for a completed job."""
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    job = JOBS[job_id]
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail=f"Job {job_id} not completed yet. Status: {job['status']}")
    if not job.get("report_url"):
        raise HTTPException(status_code=404, detail="Report not available")
    return FileResponse(job["report_url"], media_type="application/pdf",
                        filename=f"{job['patient_id']}_OncoPanther_Report.pdf")


# ── Background pipeline runners ──────────────────────────────────────────────
def _run_pgx_pipeline(job_id, patient_id, vcf_path, guidelines, physician, diagnosis):
    """Run PharmCAT PGx stepmode in background."""
    try:
        JOBS[job_id]["status"] = "running"
        job_outdir = OUTDIR / job_id / patient_id

        # Build CSV samplesheet
        pgx_csv = UPLOAD_DIR / f"{job_id}_pgx.csv"
        with open(pgx_csv, "w") as f:
            f.write(f"patient_id,vcFile\n{patient_id},{vcf_path}\n")

        # Build meta CSV
        meta_csv = UPLOAD_DIR / f"{job_id}_meta.csv"
        with open(meta_csv, "w") as f:
            f.write("Identifier,SampleID,Gender,Dob,Ethnicity,Diagnosis,vcFile\n")
            f.write(f"{patient_id},{patient_id},Unknown,Unknown,Unknown,{diagnosis or 'WES'},{vcf_path}\n")

        cmd = [
            "nextflow", "run", str(PANTHER_DIR / "main.nf"),
            "-c", str(PANTHER_DIR / "local.config"),
            "--stepmode", "--exec", "pgx",
            "--pgxVcf", str(pgx_csv),
            f"--pgxSources", guidelines,
            "--metaPatients", str(meta_csv),
            "--outdir", str(job_outdir),
            "-profile", "conda", "-resume",
        ]
        result = subprocess.run(cmd, cwd=str(PANTHER_DIR),
                                capture_output=True, text=True, timeout=3600)

        if result.returncode == 0:
            # Parse results
            from demo_app.app import parse_pharmcat_results
            gene_r, drug_r = parse_pharmcat_results(job_outdir, patient_id)
            pdf_path = job_outdir / "Reporting" / "PGx" / f"{patient_id}_PGx.pdf"

            JOBS[job_id].update({
                "status": "completed",
                "completed_at": datetime.utcnow().isoformat(),
                "pgx_results": {"genes": gene_r, "drugs": drug_r},
                "report_url": str(pdf_path) if pdf_path.exists() else None,
            })
        else:
            JOBS[job_id].update({
                "status": "failed",
                "completed_at": datetime.utcnow().isoformat(),
                "error": result.stderr[-2000:],
            })

    except Exception as e:
        JOBS[job_id].update({
            "status": "failed",
            "completed_at": datetime.utcnow().isoformat(),
            "error": str(e),
        })


def _run_full_pipeline(job_id, patient_id, r1, r2, guidelines):
    """Run full Nextflow pipeline in background."""
    try:
        JOBS[job_id]["status"] = "running"
        job_outdir = OUTDIR / job_id / patient_id

        # Build assembly CSV
        asm_csv = UPLOAD_DIR / f"{job_id}_assembly.csv"
        with open(asm_csv, "w") as f:
            f.write(f"patient_id,R1,R2\n{patient_id},{r1},{r2}\n")

        meta_csv = UPLOAD_DIR / f"{job_id}_meta.csv"
        with open(meta_csv, "w") as f:
            f.write("Identifier,SampleID,Gender,Dob,Ethnicity,Diagnosis,vcFile\n")
            f.write(f"{patient_id},{patient_id},Unknown,Unknown,Unknown,WES,\n")

        cmd = [
            "nextflow", "run", str(PANTHER_DIR / "main.nf"),
            "-c", str(PANTHER_DIR / "local.config"),
            "--fullmode",
            "--input", str(asm_csv),
            "--reference", "/refs/GRCh38/GRCh38_full_analysis_set.fna",
            "--pgx", f"--pgxSources", guidelines,
            "--metaPatients", str(meta_csv),
            "--outdir", str(job_outdir),
            "-profile", "conda", "-resume",
        ]
        result = subprocess.run(cmd, cwd=str(PANTHER_DIR),
                                capture_output=True, text=True, timeout=14400)

        if result.returncode == 0:
            from demo_app.app import parse_pharmcat_results
            gene_r, drug_r = parse_pharmcat_results(job_outdir, patient_id)
            pdf_path = job_outdir / "Reporting" / "PGx" / f"{patient_id}_PGx.pdf"
            JOBS[job_id].update({
                "status": "completed",
                "completed_at": datetime.utcnow().isoformat(),
                "pgx_results": {"genes": gene_r, "drugs": drug_r},
                "report_url": str(pdf_path) if pdf_path.exists() else None,
            })
        else:
            JOBS[job_id].update({
                "status": "failed",
                "completed_at": datetime.utcnow().isoformat(),
                "error": result.stderr[-2000:],
            })

    except Exception as e:
        JOBS[job_id].update({
            "status": "failed",
            "completed_at": datetime.utcnow().isoformat(),
            "error": str(e),
        })
