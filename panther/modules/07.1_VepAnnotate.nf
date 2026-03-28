// Module files for OncoPanther pipeline

// Vep Cache Download 


process VepAnnotation {
    tag "ANNOTATE ${vcf} WITH VEP"
    publishDir "${params.outdir}/annotation/", mode: 'copy'

    // Use pre-built vep_env (avoids OOM from creating new env during pipeline run)
    conda "base"
    container "${workflow.containerEngine == 'singularity'
        ? 'docker://ensemblorg/ensembl-vep:latest'
        : 'ensemblorg/ensembl-vep:latest'}"

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
    path "*.vcf.gz", emit: vcf
    path "*.html", emit: report
    path "*.vcf.gz.tbi", emit: tbi

    script:
    // Set cache flags using ternary operator
    def cachetypeArg = cachetype ? "--${cachetype}" : ""
    def cacheVersionArg = cacheversion ? " --cache_version ${cacheversion}" : ""

    // Optional ClinVar custom annotation
    def clinvarArg = params.clinvar ? "--custom ${params.clinvar},ClinVar,vcf,exact,0,CLNSIG,CLNREVSTAT,CLNDN" : ""
    // Optional SpliceAI plugin
    def spliceaiArg = params.spliceai ? "--plugin SpliceAI,snv=${params.spliceai}" : ""

    """
    vep \\
    --input_file ${vcf} \\
    --output_file ${vcf.simpleName}_vep.vcf.gz \\
    --format vcf \\
    --everything \\
    --vcf \\
    --species ${species} \\
    --cache \\
    --dir_cache ${cachedir} \\
    --fasta ${fasta} \\
    --offline \\
    --assembly ${assembly} \\
    --stats_file ${vcf.simpleName}_vep.html \\
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
