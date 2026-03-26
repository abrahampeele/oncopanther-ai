// Module files for OncoPanther pipeline
// PharmCAT VCF Preprocessor - Normalize VCF for pharmacogenomic analysis

process PharmcatPreprocess {
    tag "PGx VCF PREPROCESSING FOR ${patient_id}"
    publishDir "${params.outdir}/PGx/preprocessed", mode: 'copy'

    conda "bioconda::pharmcat3=3.1.1"

    container "${workflow.containerEngine == 'singularity'
        ? 'docker://pgkb/pharmcat:3.1.1'
        : 'pgkb/pharmcat:3.1.1'}"

    input:
    tuple val(patient_id), path(vcfFile), path(vcfIndex)
    path(pgxRefGenome)

    output:
    tuple val(patient_id), path("${patient_id}.preprocessed.vcf.bgz"), emit: preprocessedVcf
    tuple val(patient_id), path("${patient_id}.missing_pgx_var.vcf"),  emit: missingPgxVars

    script:
    def refArg = pgxRefGenome.name != 'NO_FILE' ? "-refFasta ${pgxRefGenome}" : ""
    """
    pharmcat_vcf_preprocessor \\
        -vcf ${vcfFile} \\
        ${refArg} \\
        -bf ${patient_id} \\
        -o .
    """
}
