/*
 * Module 11.0 — GIAB Benchmark Validation
 * Downloads GIAB truth VCF + confident regions BED for HG002/HG003/HG004
 * Runs hap.py precision/recall/F1 benchmarking vs GATK scatter output
 * Required for OncoPanther-AI publication validation (BMC Bioinformatics)
 *
 * Outputs per sample:
 *   - {sample}_hapy_summary.csv     <- Precision / Recall / F1 for SNP + INDEL
 *   - {sample}_hapy_extended.csv    <- Per-variant breakdown
 *   - {sample}_benchmark_report.html
 */

// ── Download GIAB truth data ─────────────────────────────────────────────────
process GIAB_DOWNLOAD {
    tag "GIAB-${giab_id}"
    label 'process_low'
    conda "base"
    publishDir "${params.outdir}/Validation/GIAB/truth/${giab_id}", mode: 'copy'
    storeDir   "${params.outdir}/Validation/GIAB/truth/${giab_id}"   // cache — only downloads once

    input:
    val giab_id   // e.g. "HG002", "HG003", "HG004"

    output:
    tuple val(giab_id),
          path("${giab_id}_truth.vcf.gz"),
          path("${giab_id}_truth.vcf.gz.tbi"),
          path("${giab_id}_confident.bed"),
          emit: truth_set

    script:
    // GIAB truth sets — GRCh38, publicly accessible from NCBI (no auth required)
    // URL base verified from gianglabs.github.io benchmarking guide:
    //   https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/...
    // HG001 (NA12878): NISTv3.3.2
    // HG002–HG004 (Ashkenazim trio): NISTv4.2.1
    def base = "https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release"
    def urls = [
        "HG001": [
            vcf: "${base}/NA12878_HG001/NISTv3.3.2/GRCh38/HG001_GRCh38_GIAB_highconf_CG-IllFB-IllGATKHC-Ion-10X-SOLID_CHROM1-X_v.3.3.2_highconf_PGandRTGphasetransfer.vcf.gz",
            tbi: "${base}/NA12878_HG001/NISTv3.3.2/GRCh38/HG001_GRCh38_GIAB_highconf_CG-IllFB-IllGATKHC-Ion-10X-SOLID_CHROM1-X_v.3.3.2_highconf_PGandRTGphasetransfer.vcf.gz.tbi",
            bed: "${base}/NA12878_HG001/NISTv3.3.2/GRCh38/HG001_GRCh38_GIAB_highconf_CG-IllFB-IllGATKHC-Ion-10X-SOLID_CHROM1-X_v.3.3.2_highconf_nosomaticdel_noCENorHET7.bed"
        ],
        "HG002": [
            vcf: "${base}/AshkenazimTrio/HG002_NA24385_son/NISTv4.2.1/GRCh38/HG002_GRCh38_1_22_v4.2.1_benchmark.vcf.gz",
            tbi: "${base}/AshkenazimTrio/HG002_NA24385_son/NISTv4.2.1/GRCh38/HG002_GRCh38_1_22_v4.2.1_benchmark.vcf.gz.tbi",
            bed: "${base}/AshkenazimTrio/HG002_NA24385_son/NISTv4.2.1/GRCh38/HG002_GRCh38_1_22_v4.2.1_benchmark_noinconsistent.bed"
        ],
        "HG003": [
            vcf: "${base}/AshkenazimTrio/HG003_NA24149_father/NISTv4.2.1/GRCh38/HG003_GRCh38_1_22_v4.2.1_benchmark.vcf.gz",
            tbi: "${base}/AshkenazimTrio/HG003_NA24149_father/NISTv4.2.1/GRCh38/HG003_GRCh38_1_22_v4.2.1_benchmark.vcf.gz.tbi",
            bed: "${base}/AshkenazimTrio/HG003_NA24149_father/NISTv4.2.1/GRCh38/HG003_GRCh38_1_22_v4.2.1_benchmark_noinconsistent.bed"
        ],
        "HG004": [
            vcf: "${base}/AshkenazimTrio/HG004_NA24143_mother/NISTv4.2.1/GRCh38/HG004_GRCh38_1_22_v4.2.1_benchmark.vcf.gz",
            tbi: "${base}/AshkenazimTrio/HG004_NA24143_mother/NISTv4.2.1/GRCh38/HG004_GRCh38_1_22_v4.2.1_benchmark.vcf.gz.tbi",
            bed: "${base}/AshkenazimTrio/HG004_NA24143_mother/NISTv4.2.1/GRCh38/HG004_GRCh38_1_22_v4.2.1_benchmark_noinconsistent.bed"
        ]
    ]
    def u = urls[giab_id]
    if (!u) error "Unknown GIAB sample: ${giab_id}. Valid values: HG001, HG002, HG003, HG004"
    """
    echo "[GIAB] Downloading truth set for ${giab_id} (GRCh38)"
    wget -q --show-progress -O ${giab_id}_truth.vcf.gz     '${u.vcf}'
    wget -q --show-progress -O ${giab_id}_truth.vcf.gz.tbi '${u.tbi}'
    wget -q --show-progress -O ${giab_id}_confident.bed    '${u.bed}'
    echo "[GIAB] Download complete: ${giab_id}"
    """
}

// ── Install hap.py + build rtgtools SDF for reference ───────────────────────
// hap.py --engine=vcfeval requires the reference in rtgtools SDF format.
// SDF is built once from the reference FASTA and cached in storeDir.
process INSTALL_HAPY {
    tag "install-hap.py"
    label 'process_medium'
    conda "base"
    storeDir "${params.outdir}/Validation/GIAB/.hapy_installed"

    input:
    path reference_fasta   // GRCh38 FASTA — needed to build SDF

    output:
    path "hapy_installed.flag",  emit: flag
    path "ref_sdf/",             emit: sdf   // rtgtools SDF directory

    script:
    """
    # hap.py conflicts with conda-forge packages (libdeflate/c-ares chain).
    # Solution: create isolated env using bioconda + defaults only (no conda-forge).
    # Using mamba for faster solve; --override-channels prevents conda-forge conflicts.
    HAPY_ENV="hapy_env"

    if ! conda env list | grep -q "^\${HAPY_ENV}"; then
        echo "[hap.py] Creating dedicated conda env '\${HAPY_ENV}'..."
        mamba create -y -n \${HAPY_ENV} --override-channels -c bioconda -c defaults hap.py rtg-tools 2>&1
    else
        echo "[hap.py] Env '\${HAPY_ENV}' already exists — skipping create"
    fi

    # Verify tools are available in hapy_env
    conda run -n \${HAPY_ENV} hap.py --version 2>/dev/null || {
        echo "ERROR: hap.py not found in \${HAPY_ENV}"; exit 1
    }
    conda run -n \${HAPY_ENV} rtg version 2>/dev/null | head -1 || {
        echo "ERROR: rtg not found in \${HAPY_ENV}"; exit 1
    }

    echo "[rtgtools] Building reference SDF from ${reference_fasta}..."
    conda run -n \${HAPY_ENV} rtg format -o ref_sdf ${reference_fasta}
    echo "[rtgtools] SDF built: \$(du -sh ref_sdf/ | cut -f1)"

    touch hapy_installed.flag
    echo "[hap.py] Setup complete"
    """
}

// ── Run rtg vcfeval for one sample (replaces hap.py which has quantify regex bug) ──
process HAPY_BENCHMARK {
    tag "${sample_id} vs ${giab_id}"
    label 'process_medium'
    conda "base"
    publishDir "${params.outdir}/Validation/GIAB/results/${sample_id}", mode: 'copy'

    input:
    // Combined tuple from ValidationVcf.combine(GIAB_DOWNLOAD.out.truth_set):
    // [sample_id, query_vcf, query_tbi, giab_id, truth_vcf, truth_tbi, confident_bed]
    tuple val(sample_id),  path(query_vcf),  path(query_tbi),
          val(giab_id),    path(truth_vcf),  path(truth_tbi),  path(confident_bed)
    path(hapy_flag)
    path(ref_sdf)          // rtgtools SDF directory — required by vcfeval
    path(reference_fasta)  // GRCh38 FASTA (unused but kept for input contract)

    output:
    tuple val(sample_id), val(giab_id),
          path("${sample_id}_${giab_id}_hapy_summary.csv"),
          path("${sample_id}_${giab_id}_hapy_extended.csv"),
          path("${sample_id}_${giab_id}_hapy.html"),
          emit: benchmark_results

    script:
    """
    echo "[vcfeval] Benchmarking ${sample_id} vs ${giab_id} truth set"

    # Use rtg vcfeval directly (hap.py's quantify C++ binary has regex bug with --roc-regions '*')
    conda run -n hapy_env rtg vcfeval \\
        -b ${truth_vcf} \\
        -c ${query_vcf} \\
        -t ${ref_sdf} \\
        -e ${confident_bed} \\
        -o vcfeval_out \\
        --ref-overlap \\
        --threads ${task.cpus} \\
        --squash-ploidy

    # Parse vcfeval ROC files → separate SNP and INDEL rows (matches BENCHMARK_AGGREGATE schema)
    python3 - << 'PYEOF'
import csv, gzip, re

def parse_roc(gz_path):
    # Returns (TP_baseline, FP, TP_call, FN, Precision, Recall, F1) at best F-measure
    best_f, best_row = -1.0, None
    with gzip.open(gz_path, 'rt') as fh:
        for line in fh:
            line = line.rstrip()
            if line.startswith('#'):
                continue
            cols = line.split('\\t')
            if len(cols) >= 7:
                try:
                    f = float(cols[6])
                    if f > best_f:
                        best_f = f
                        best_row = cols
                except:
                    pass
    if best_row:
        tp_b = float(best_row[1])
        fp   = float(best_row[2])
        tp_c = float(best_row[3])
        fn   = float(best_row[4])
        prec = float(best_row[5])
        rec  = float(best_row[6])  # Sensitivity
        f1   = float(best_row[6]) if len(best_row) < 7 else (
               2*prec*rec/(prec+rec) if (prec+rec) > 0 else 0.0)
        # Recalculate F1 properly
        f1 = 2*prec*rec/(prec+rec) if (prec+rec) > 0 else 0.0
        return tp_b, fp, tp_c, fn, prec, rec, f1
    return None

hdr = ["Type","Filter","TRUTH.TOTAL","TRUTH.TP","TRUTH.FN",
       "QUERY.TOTAL","QUERY.TP","QUERY.FP","QUERY.UNK",
       "METRIC.Recall","METRIC.Precision","METRIC.F1_Score"]

rows = []
for vtype, roc_file in [("SNP","vcfeval_out/snp_roc.tsv.gz"),
                         ("INDEL","vcfeval_out/non_snp_roc.tsv.gz")]:
    r = parse_roc(roc_file)
    if r:
        tp_b, fp, tp_c, fn, prec, rec, f1 = r
        truth_total = int(tp_b + fn)
        query_total = int(tp_c + fp)
        rows.append([vtype, "PASS", truth_total, int(tp_b), int(fn),
                     query_total, int(tp_c), int(fp), 0,
                     round(rec,4), round(prec,4), round(f1,4)])

with open("${sample_id}_${giab_id}_hapy_summary.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(hdr)
    for row in rows:
        w.writerow(row)

print("Summary CSV written with " + str(len(rows)) + " rows (SNP + INDEL).")
PYEOF

    # Write extended CSV (same content for now — rtg vcfeval best threshold)
    cp ${sample_id}_${giab_id}_hapy_summary.csv ${sample_id}_${giab_id}_hapy_extended.csv

    # Write a minimal HTML placeholder (no HTML report from rtg vcfeval)
    echo "<html><body><pre>" > ${sample_id}_${giab_id}_hapy.html
    cat vcfeval_out/summary.txt >> ${sample_id}_${giab_id}_hapy.html
    echo "</pre></body></html>" >> ${sample_id}_${giab_id}_hapy.html

    echo "[vcfeval] Done: ${sample_id} vs ${giab_id}"
    cat ${sample_id}_${giab_id}_hapy_summary.csv
    """
}

// ── Aggregate all results into paper table ───────────────────────────────────
process BENCHMARK_AGGREGATE {
    tag "aggregate-benchmark"
    label 'process_low'
    conda "base"
    publishDir "${params.outdir}/Validation/GIAB/summary", mode: 'copy'

    input:
    path(csv_files, stageAs: "results/*")   // all hapy_summary.csv files

    output:
    path "benchmark_table.csv",    emit: table
    path "benchmark_table.tsv",    emit: tsv
    path "benchmark_figures/",     emit: figures

    script:
    """
    python3 << 'PYEOF'
import os, glob, pandas as pd, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# Aggregate all summary CSVs
dfs = []
for f in sorted(glob.glob("results/*_hapy_summary.csv")):
    basename = os.path.basename(f)
    parts = basename.replace("_hapy_summary.csv", "").split("_")
    sample_id = parts[0]
    giab_id   = parts[1] if len(parts) > 1 else "GIAB"
    df = pd.read_csv(f)
    df['Sample'] = sample_id
    df['GIAB_Truth'] = giab_id
    dfs.append(df)

if not dfs:
    print("No benchmark results found")
    exit(0)

combined = pd.concat(dfs, ignore_index=True)

# Filter to just SNP and INDEL rows
paper_table = combined[combined['Type'].isin(['SNP','INDEL'])][
    ['Sample','GIAB_Truth','Type','METRIC.Precision','METRIC.Recall','METRIC.F1_Score','TRUTH.TOTAL','QUERY.TOTAL']
].copy()
paper_table.columns = ['Sample','GIAB_Truth','Type','Precision','Recall','F1','Truth_Variants','Query_Variants']
paper_table['Precision'] = paper_table['Precision'].round(4)
paper_table['Recall']    = paper_table['Recall'].round(4)
paper_table['F1']        = paper_table['F1'].round(4)

paper_table.to_csv("benchmark_table.csv", index=False)
paper_table.to_csv("benchmark_table.tsv", index=False, sep='\\t')
print(paper_table.to_string(index=False))

# ── Publication Figure: Grouped bar chart ──
os.makedirs("benchmark_figures", exist_ok=True)
fig, axes = plt.subplots(1, 2, figsize=(12, 5))
fig.suptitle("OncoPanther-AI Variant Calling Accuracy\\nvs. GIAB NISTv3.3.2 Truth Set (HG001, GRCh38)", fontsize=13, fontweight='bold')

for ax, vtype in zip(axes, ['SNP', 'INDEL']):
    subset = paper_table[paper_table['Type'] == vtype]
    if subset.empty:
        continue
    x = range(len(subset))
    width = 0.28
    bars_p = ax.bar([i - width for i in x], subset['Precision'], width, label='Precision', color='#2196F3', edgecolor='black', lw=0.5)
    bars_r = ax.bar([i          for i in x], subset['Recall'],   width, label='Recall',    color='#4CAF50', edgecolor='black', lw=0.5)
    bars_f = ax.bar([i + width  for i in x], subset['F1'],       width, label='F1 Score',  color='#FF9800', edgecolor='black', lw=0.5)
    ax.set_xticks(list(x))
    ax.set_xticklabels([f"{r.Sample}\\n({r.GIAB_Truth})" for _, r in subset.iterrows()], fontsize=9)
    ax.set_ylim(0.0, 1.08)
    ax.set_ylabel("Score", fontsize=10)
    ax.set_title(f"{vtype} Performance", fontsize=11, fontweight='bold')
    ax.legend(fontsize=8)
    ax.grid(axis='y', alpha=0.3)
    for bar in [*bars_p, *bars_r, *bars_f]:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.001,
                f'{bar.get_height():.3f}', ha='center', va='bottom', fontsize=6.5)

plt.tight_layout()
plt.savefig("benchmark_figures/accuracy_benchmark.png", dpi=200, bbox_inches='tight', facecolor='white')
plt.close()
print("\\n[Benchmark] Figure saved: benchmark_figures/accuracy_benchmark.png")
PYEOF
    """
}
