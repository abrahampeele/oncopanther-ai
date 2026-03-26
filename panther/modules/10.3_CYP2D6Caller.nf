// Module files for OncoPanther-AI pipeline
// CYP2D6 Star Allele Caller using Cyrius (Illumina)
// Calls CYP2D6 structural variants from WGS BAM files
// Output: PharmCAT-compatible outside calls TSV

process CYP2D6Call {
    tag "CYP2D6 CALLING FOR ${patient_id}"
    publishDir "${params.outdir}/PGx/cyp2d6", mode: 'copy'

    input:
    tuple val(patient_id), path(bamFile), path(bamIndex)

    output:
    tuple val(patient_id), path("${patient_id}.cyp2d6_outsidecalls.tsv"), emit: outsideCalls
    tuple val(patient_id), path("${patient_id}.cyrius_genotype.tsv"),     emit: cyriusRaw
    tuple val(patient_id), path("${patient_id}.cyrius_genotype.json"),    emit: cyriusJson, optional: true

    script:
    """
    #!/usr/bin/env python3
    import subprocess
    import os
    import csv
    import json

    patient_id = "${patient_id}"
    bam_file = "${bamFile}"

    ##########################################################################
    # Step 1: Create Cyrius manifest file (list of BAM paths)
    ##########################################################################
    manifest_file = f"{patient_id}_manifest.txt"
    with open(manifest_file, "w") as f:
        f.write(os.path.abspath(bam_file) + "\\n")

    ##########################################################################
    # Step 2: Run Cyrius
    ##########################################################################
    cyrius_cmd = [
        "cyrius",
        "-m", manifest_file,
        "-g", "38",
        "-o", ".",
        "-p", patient_id,
        "-t", "1"
    ]

    print(f"[OncoPanther-AI] Running Cyrius CYP2D6 caller for {patient_id}...")
    print(f"[OncoPanther-AI] Command: {' '.join(cyrius_cmd)}")

    result = subprocess.run(cyrius_cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr)

    ##########################################################################
    # Step 3: Parse Cyrius output TSV
    ##########################################################################
    cyrius_tsv = f"{patient_id}.tsv"
    genotype = "N/A"
    filter_status = "NO_CALL"

    if os.path.exists(cyrius_tsv):
        with open(cyrius_tsv, "r") as f:
            reader = csv.DictReader(f, delimiter="\\t")
            for row in reader:
                genotype = row.get("Genotype", "None")
                filter_status = row.get("Filter", "NO_CALL")
                break

        # Rename to standard output name
        os.rename(cyrius_tsv, f"{patient_id}.cyrius_genotype.tsv")
    else:
        # Create empty genotype file if Cyrius failed (e.g., insufficient data)
        print(f"[OncoPanther-AI] WARNING: Cyrius did not produce output for {patient_id}")
        print(f"[OncoPanther-AI] This may be due to insufficient coverage on chr22 (CYP2D6 region)")
        with open(f"{patient_id}.cyrius_genotype.tsv", "w") as f:
            f.write("Sample\\tGenotype\\tFilter\\n")
            f.write(f"{patient_id}\\tNone\\tNO_DATA\\n")
        genotype = "None"
        filter_status = "NO_DATA"

    # Rename JSON if exists
    cyrius_json = f"{patient_id}.json"
    if os.path.exists(cyrius_json):
        os.rename(cyrius_json, f"{patient_id}.cyrius_genotype.json")

    print(f"[OncoPanther-AI] CYP2D6 Result: {genotype} (Filter: {filter_status})")

    ##########################################################################
    # Step 4: Convert to PharmCAT Outside Calls format
    # Format: gene<TAB>diplotype
    # See: https://pharmcat.clinpgx.org/using/Outside-Call-Format/
    ##########################################################################
    outside_calls_file = f"{patient_id}.cyp2d6_outsidecalls.tsv"

    with open(outside_calls_file, "w") as f:
        if genotype and genotype != "None" and filter_status not in ["NO_CALL", "NO_DATA"]:
            # Clean up Cyrius notation for PharmCAT
            diplotype = genotype.strip()

            # Handle Cyrius copy number notation: *1x3 -> *1\\u2265 3
            # PharmCAT uses the >= (\\u2265) symbol for copy numbers
            import re
            diplotype = re.sub(r'\\*(\\d+)x(\\d+)', lambda m: f'*{m.group(1)}\\u22653' if int(m.group(2)) >= 3 else f'*{m.group(1)}x{m.group(2)}', diplotype)

            # Handle underscore notation (ambiguous haplotype assignment)
            # e.g., *1_*2_*68 means multiple possible arrangements
            if "_" in diplotype and "/" not in diplotype:
                # Cannot determine phase — report as-is with a note
                f.write(f"CYP2D6\\t{diplotype}\\n")
                print(f"[OncoPanther-AI] Note: CYP2D6 call has ambiguous phasing: {diplotype}")
            else:
                f.write(f"CYP2D6\\t{diplotype}\\n")

            print(f"[OncoPanther-AI] PharmCAT outside call written: CYP2D6\\t{diplotype}")
        else:
            # Write empty outside calls (PharmCAT will use VCF-based calling)
            f.write("# No CYP2D6 structural variant call available\\n")
            f.write("# Cyrius filter: {filter_status}\\n".format(filter_status=filter_status))
            print(f"[OncoPanther-AI] No confident CYP2D6 call — PharmCAT will use VCF-based calling")

    print(f"[OncoPanther-AI] CYP2D6 analysis complete for {patient_id}")
    """
}
