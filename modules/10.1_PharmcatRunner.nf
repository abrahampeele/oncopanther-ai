// Module files for OncoPanther-AI pipeline
// PharmCAT Runner - Execute pharmacogenomic analysis
// Supports per-sample outside calls from CYP2D6 caller (Cyrius)
// Uses Java JAR directly when outside calls are provided (Python wrapper doesn't support -po)

process PharmcatAnalysis {
    tag "PGx ANALYSIS FOR ${patient_id}"
    publishDir "${params.outdir}/PGx/pharmcat", mode: 'copy'

    container "${workflow.containerEngine == 'singularity'
        ? 'docker://pgkb/pharmcat:3.1.1'
        : 'pgkb/pharmcat:3.1.1'}"

    input:
    tuple val(patient_id), path(preprocessedVcf), path(outsideCalls)

    output:
    tuple val(patient_id), path("${patient_id}.match.json"),     emit: matchJson
    tuple val(patient_id), path("${patient_id}.phenotype.json"), emit: phenotypeJson
    tuple val(patient_id), path("${patient_id}.report.html"),    emit: reportHtml
    tuple val(patient_id), path("${patient_id}.report.json"),    emit: reportJson

    script:
    def hasOutsideCalls = outsideCalls.name != "NO_OUTSIDE_CALLS"
    def pharmcatJar = new File("${projectDir}/pharmcat.jar").absolutePath

    if (hasOutsideCalls) {
        // Use Java JAR directly — the Python wrapper doesn't support -po (outside calls)
        """
        # Run PharmCAT Matcher
        java -jar ${pharmcatJar} \\
            -vcf ${preprocessedVcf} \\
            -po ${outsideCalls} \\
            -bf ${patient_id} \\
            -o . \\
            -reporterJson \\
            -reporterHtml
        """
    } else {
        // Use Python wrapper (simpler, no outside calls needed)
        """
        pharmcat_pipeline \\
            ${preprocessedVcf} \\
            -bf ${patient_id} \\
            -o . \\
            -reporterJson \\
            -reporterHtml
        """
    }
}
