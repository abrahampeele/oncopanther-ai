// Module files for OncoPanther pipeline

// GATK variant calling for Recalibrated mapped reads  

process CallVariant {

    tag "Variant Calling with Gatk HaplotypeCaller"
    publishDir "${params.outdir}/Variants/gatk", mode: 'copy'

    conda "bioconda::gatk4=4.4.0.0"

    input:
    path ref
    path dic
    path fai
    tuple val(patient_id), path(ReclBamFile), path(Bamidx)
    path bedtarget


    output:
    tuple val(patient_id),
          path("${ReclBamFile.baseName}.*.HC.vcf.gz"),
          path("*.{tbi,idx}"),
          emit: "CallVariantvcf"

    script:
    def hasBed    = bedtarget.name != 'NO_FILE'
    def hasRegion = params.region != null

    def regions = hasRegion ? (params.region instanceof List ? params.region : params.region.split(','))  : []

    def intervalArg = hasBed  ? "-L ${bedtarget}" : hasRegion ? regions.collect { "-L $it" }.join(' ') : ""
    def regionTag   = hasBed  ? "bedtargeted"     : hasRegion ? regions.collect { it.split(':')[0] }.join('_')  : "full"

   """
    gatk HaplotypeCaller \\
        --native-pair-hmm-threads ${task.cpus} \\
        -R ${ref} \\
        -I ${ReclBamFile} \\
        -O ${ReclBamFile.baseName}.${regionTag}.HC.vcf.gz \\
        ${intervalArg}
    """

}

// Create GVCF files

process CreateGVCF {
    tag "CREATE GVCF with Gatk HaplotypeCaller"
    publishDir "${params.outdir}/Variants/gatk", mode: 'copy', enabled: params.keepinter 

    conda "bioconda::gatk4=4.4.0.0"
    container "${workflow.containerEngine == 'singularity'
        ? "docker://broadinstitute/gatk:latest"
        : "broadinstitute/gatk:latest"}"

    input:
    path ref
    path dic
    path fai
    tuple val(patient_id), path(ReclBamFile), path(Bamidx)
    path bedtarget
    
    output:
    tuple val(patient_id), path("*.g.vcf.gz"), path("*.{tbi,idx}")	, emit: "g_vcf_Recal"

    script:
    def hasBed = bedtarget.name != 'NO_FILE'
    def hasRegion = params.region != null

    def intervalArg = hasBed ? "-L ${bedtarget}"  : hasRegion ? "-L ${params.region}"       : ""
    def regionTag   = hasBed ? "bedtargeted"      : hasRegion ? params.region.split(':')[0] : "full"

    """
    gatk HaplotypeCaller \\
        --native-pair-hmm-threads ${task.cpus} \\
        --reference ${ref} \\
        --input ${ReclBamFile} \\
        --output ${ReclBamFile.baseName}.${regionTag}.g.vcf.gz \\
        --emit-ref-confidence GVCF \\
        ${intervalArg}
    """
}

// Combining GVCFs 

process CombineGvcfs {
    tag "COMBINE GVCF files with Gatk HaplotypeCaller"
    publishDir "${params.outdir}/Variants/gatk", mode: 'copy'

    conda "bioconda::gatk4=4.4.0.0"
    container "${workflow.containerEngine == 'singularity'
        ? "docker://broadinstitute/gatk:latest"
        : "broadinstitute/gatk:latest"}"

    input:
    path ref
    path dic
    path fai
    tuple val(patient_id), path(GvcfFiles), path(IDXofGvcf)
    
    output:
    tuple val(patient_id), path("cohort_oncoPanther-*.g.vcf.gz"), path("*.{tbi,idx}"), emit: "CohortVcf"
    
    script:
    def regionTag   = params.bedtarget ? "bedtargeted"      : params.region ? params.region.split(':')[0] : "full"
    
    """
    gatk CombineGVCFs \\
	--reference ${ref} \\
	--variant ${GvcfFiles.join(' --variant ')} \\
        --output cohort_oncoPanther-${regionTag}.g.vcf.gz
    """
}
 
// Generating Genotypes of GVCFs

process GenotypeGvcfs {
    tag "GENERATING GENOTYPES OF GVCF"
    publishDir "${params.outdir}/Variants/gatk", mode: 'copy'

    conda "bioconda::gatk4=4.4.0.0"
    container "${workflow.containerEngine == 'singularity'
        ? "docker://broadinstitute/gatk:latest"
        : "broadinstitute/gatk:latest"}"

    input:
    path ref
    path dic
    path fai
    tuple val(patient_id), path(CombinedFile), path(gzidx)
    
    output:
    tuple val(patient_id), path("cohort_oncoPanther-*.vcf.gz"), path("*.{tbi,idx}")	, emit: "CombinedGENOTYPES"
    
    script:
    
    def regionTag   = params.bedtarget ? "bedtargeted"      : params.region ? params.region.split(':')[0] : "full"

    """
    gatk GenotypeGVCFs \\
	--reference ${ref} \\
	--variant ${CombinedFile} \\
        --output cohort_oncoPanther-${regionTag}.vcf.gz
    """
}


// ── SCATTER / GATHER  ── parallel chromosome-level variant calling ──────────

process ScatterCallVariant {

    tag "HC scatter: ${patient_id} | ${chrom}"
    cpus 2

    conda "bioconda::gatk4=4.4.0.0"

    input:
    path ref
    path dic
    path fai
    tuple val(patient_id), path(bamFile), path(bamIdx), val(chrom)

    output:
    tuple val(patient_id),
          path("${bamFile.baseName}.${chrom}.HC.vcf.gz"),
          path("${bamFile.baseName}.${chrom}.HC.vcf.gz.tbi"),
          emit: "scatterVcf"

    script:
    """
    gatk HaplotypeCaller         --native-pair-hmm-threads ${task.cpus}         -R ${ref}         -I ${bamFile}         -L ${chrom}         -O ${bamFile.baseName}.${chrom}.HC.vcf.gz
    """
}


process GatherVcfs {

    tag "Gather VCFs: ${patient_id}"
    publishDir "${params.outdir}/Variants/gatk", mode: 'copy'
    cpus 1

    conda "bioconda::gatk4=4.4.0.0"

    input:
    tuple val(patient_id), path(vcfs), path(tbis)

    output:
    tuple val(patient_id),
          path("${patient_id}_oncoPanther.full.HC.vcf.gz"),
          path("${patient_id}_oncoPanther.full.HC.vcf.gz.tbi"),
          emit: "CallVariantvcf"

    script:
    // Sort VCFs by canonical chromosome order
    def chrOrder = ['chr1','chr2','chr3','chr4','chr5','chr6','chr7','chr8','chr9',
                    'chr10','chr11','chr12','chr13','chr14','chr15','chr16','chr17',
                    'chr18','chr19','chr20','chr21','chr22','chrX','chrY','chrM']
    def vcfList   = (vcfs instanceof List) ? vcfs : [vcfs]
    def sortedVcfs = vcfList.sort { a, b ->
        def tokA = a.name.tokenize('.')
        def tokB = b.name.tokenize('.')
        def chrA = tokA.find { it.startsWith('chr') } ?: a.name
        def chrB = tokB.find { it.startsWith('chr') } ?: b.name
        def idxA = chrOrder.indexOf(chrA); if (idxA < 0) idxA = 999
        def idxB = chrOrder.indexOf(chrB); if (idxB < 0) idxB = 999
        idxA <=> idxB
    }
    def vcfArgs = sortedVcfs.collect { it.toString() }.join(' ')
    """
    bcftools concat -a -D --threads ${task.cpus} -Oz -o ${patient_id}_oncoPanther.full.HC.vcf.gz ${vcfArgs}
    bcftools index --tbi ${patient_id}_oncoPanther.full.HC.vcf.gz
    """
}
