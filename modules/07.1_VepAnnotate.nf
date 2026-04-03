// Module files for OncoPanther pipeline

// Vep Cache Download 


process VepAnnotation {
    tag "ANNOTATE ${vcf} WITH VEP"
    publishDir "${params.outdir}/annotation/", mode: 'copy'

    // FIX: pinned version — never use 'latest' for reproducibility (gianglabs Art.9)
    conda 'bioconda::ensembl-vep=114.2 bioconda::bcftools=1.21'
    container "${workflow.containerEngine == 'singularity'
        ? 'docker://ensemblorg/ensembl-vep:release_114.2'
        : 'ensemblorg/ensembl-vep:release_114.2'}"

    input:
    tuple val(patient_id), path(vcf)
    path fasta
    path genomeindex
    val cachedir
    val species
    val assembly
    val cachetype
    val cacheversion

    output:
    tuple val(patient_id), path("*_vep.vcf.gz"),     emit: vcf
    path "*_vep.html",                                emit: report
    path "*_vep.vcf.gz.tbi",                         emit: tbi

    script:
    def cachetypeArg    = cachetype   ? "--${cachetype}"                : ""
    def cacheVersionArg = cacheversion ? "--cache_version ${cacheversion}" : ""
    // Optional plugins — controlled by params
    def clinvarArg  = params.clinvar  ? "--custom ${params.clinvar},ClinVar,vcf,exact,0,CLNSIG,CLNREVSTAT,CLNDN" : ""
    def spliceaiArg = params.spliceai ? "--plugin SpliceAI,snv=${params.spliceai}" : ""

    """
    set -euo pipefail

    # FIX: bcftools norm before VEP — left-align + split multi-allelic sites
    # Ensures correct annotation of indels and multi-allelic variants (gianglabs Art.7)
    bcftools norm \\
        --fasta-ref ${fasta} \\
        --multiallelics -any \\
        --output-type z \\
        --output ${vcf.simpleName}_norm.vcf.gz \\
        --threads ${task.cpus} \\
        ${vcf}
    tabix -p vcf ${vcf.simpleName}_norm.vcf.gz

    # VEP annotation — pinned cache v114, clinical flags
    vep \\
        --input_file  ${vcf.simpleName}_norm.vcf.gz \\
        --output_file ${vcf.simpleName}_vep.vcf.gz \\
        --format vcf \\
        --everything \\
        --pick_allele_gene \\
        --vcf \\
        --species   ${species} \\
        --cache \\
        --dir_cache ${cachedir} \\
        --fasta     ${fasta} \\
        --offline \\
        --assembly  ${assembly} \\
        --stats_file    ${vcf.simpleName}_vep.html \\
        --force_overwrite \\
        --compress_output bgzip \\
        --fork ${task.cpus} \\
        ${cachetypeArg} \\
        ${cacheVersionArg} \\
        ${clinvarArg} \\
        ${spliceaiArg}

    tabix -p vcf ${vcf.simpleName}_vep.vcf.gz
    """
}
