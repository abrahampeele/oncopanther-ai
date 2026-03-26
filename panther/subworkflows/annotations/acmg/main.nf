// OncoPanther-PGx | Subworkflow: ACMG/AMP Variant Classification
// Chains VEP-annotated VCFs through the ACMG/AMP 2015 classifier
// Produces per-patient TSV + JSON with clinical significance tiers

include { AcmgClassify } from '../../../modules/07.3_AcmgClassify'

workflow ACMG_CLASSIFY {

    take:
    vep_vcf_ch   // channel: [ patient_id, vcf.gz, tbi ]

    main:

    // Validate required params
    if (!params.acmg) {
        log.warn "[OncoPanther] ACMG classification skipped (--acmg not set)"
    }

    AcmgClassify(vep_vcf_ch)

    emit:
    acmg_tsv   = AcmgClassify.out.acmg_tsv
    acmg_json  = AcmgClassify.out.acmg_json
    vcf        = AcmgClassify.out.vcf
}
