# OncoPanther-AI — Partner Deployment Guide

## Prerequisites
- Docker Desktop installed ([download](https://www.docker.com/products/docker-desktop/))
- 60 GB free disk space
- Internet connection (first run only)

---

## Day 1 — First Time Setup (One Command)

```bash
docker run -d \
  --name oncopanther \
  -p 8501:8501 \
  -p 8000:8000 \
  -v oncopanther-refs:/refs \
  -v oncopanther-data:/data \
  oncopanther/oncopanther-ai:latest
```

Then open your browser → **http://localhost:8501**

You will see a **setup progress page** — reference data downloads automatically:

```
✅ GRCh38 Reference Genome (3.1 GB)    ← ~30 min
✅ BWA-MEM2 Index (8 GB)               ← ~1-2 hrs
✅ VEP GRCh38 Cache (25 GB)            ← ~4-6 hrs
✅ ClinVar VCF (1 GB)                  ← ~15 min
✅ GATK Dictionary (10 MB)             ← ~1 min
```

**Total first-run time: 6-8 hours** (can run overnight)

When complete → browser automatically redirects to OncoPanther app.

---

## Day 2, 3, 4... — Every Time

```bash
docker start oncopanther
```

Open browser → **http://localhost:8501** → **Ready instantly** ✅

No downloads. No setup. References are cached in Docker volume forever.

---

## Using the App

### Upload FASTQ (Full Pipeline — 1-4 hrs)
1. Open http://localhost:8501
2. Fill patient details (Name, ID, DOB, Physician)
3. Select **🧬 FASTQ → Full Pipeline**
4. Upload R1 + R2 FASTQ.GZ files
5. Click **Run Analysis**
6. Watch live pipeline log
7. Download clinical PDF report

### Upload VCF (PGx Only — 5-10 min)
1. Open http://localhost:8501
2. Select **📤 Upload VCF → PGx Analysis**
3. Upload your VCF.GZ file
4. Click **Run Analysis**
5. Download PGx report

---

## REST API (for LIMS integration)

```bash
# Submit VCF for PGx analysis
curl -X POST http://localhost:8000/api/v1/analyze/vcf \
  -F "vcf_file=@patient.vcf.gz" \
  -F "patient_id=PT001" \
  -F "guidelines=CPIC"

# Response:
# {"job_id": "A3F9B2C1", "status": "queued", "message": "..."}

# Check status
curl http://localhost:8000/api/v1/jobs/A3F9B2C1

# Download report when done
curl http://localhost:8000/api/v1/jobs/A3F9B2C1/report -o report.pdf
```

Full API docs: **http://localhost:8000/docs**

---

## System Requirements

| | Minimum | Recommended |
|-|---------|-------------|
| CPU | 4 cores | 16 cores |
| RAM | 16 GB | 32 GB |
| Disk | 60 GB free | 200 GB |
| OS | Windows 10/11, macOS, Linux | Any |
| Docker | 24+ | 24+ |

---

## Troubleshooting

```bash
# View logs
docker logs oncopanther --tail 50

# Check setup progress
docker exec oncopanther cat /refs/setup.log | tail -20

# Restart app
docker restart oncopanther

# Check disk space
docker exec oncopanther df -h /refs
```

---

## Support
Contact OncoPanther team | Industry Partner: SecuAI
