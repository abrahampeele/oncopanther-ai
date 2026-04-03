# OncoPanther-AI - Partner Deployment Guide

## Prerequisites
- Docker Desktop installed
- 60 GB free disk space
- Internet connection (first run only)

## Day 1 - First Time Setup

```bash
docker run -d \
  --name oncopanther \
  -p 8501:8501 \
  -p 8000:8000 \
  -v oncopanther-refs:/refs \
  -v oncopanther-data:/data \
  abpeele/oncopanther-ai:latest
```

Open http://localhost:8501 and let the automatic reference setup finish.

## Later Runs

```bash
docker start oncopanther
```
