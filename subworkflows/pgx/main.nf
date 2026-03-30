// Pharmacogenomics (PGx) subworkflow
// Orchestrates CYP2D6 calling (Cyrius), PharmCAT VCF preprocessing, analysis, and PGx PDF report generation

include { OncoPantherWelcome      } from '../../.logos'
include { OncoPantherPgxOutput    } from '../../.logos'

include { CYP2D6Call           } from '../../modules/10.3_CYP2D6Caller.nf'
include { PharmcatPreprocess   } from '../../modules/10.0_PharmcatPreprocess.nf'
include { PharmcatAnalysis     } from '../../modules/10.1_PharmcatRunner.nf'
include { GeneratePgxReport    } from '../../modules/10.2_PgxReporting.nf'

workflow PGX_ANALYSIS {

    take:
    vcfChannel             // tuple val(patient_id), path(vcf), path(vcfIdx)
    pgxRefGenome           // path to GRCh38 reference for PharmCAT (or NO_FILE)
    metaPipeExecYaml       // reporting metadata channel (can be empty)
    bamChannel             // tuple val(patient_id), path(bam), path(bai) — for CYP2D6 (optional, can be empty)

    main:

    // Validate required parameters
    if (!params.pgxVcf && !params.fullmode) {
        OncoPantherWelcome()
        log.info """
        \033[31m Please specify valid parameters for PGx analysis:\n
        \033[32m --pgxVcf\033[37m        <path-to-csv>       CSV with patient_id and vcFile columns
        \033[32m --pgxRefGenome\033[37m   <path-to-fasta>     GRCh38 reference FASTA (optional)
        \033[32m --pgxSources\033[37m     <CPIC|DPWG|FDA>     Recommendation sources (default: CPIC)
        \033[32m --pgxOutsideCalls\033[37m <path-to-tsv>      Outside calls for CYP2D6 (optional)
        \033[32m --cyp2d6\033[37m                              Enable CYP2D6 star allele calling via Cyrius (requires BAM files)
        \033[32m --pgxBam\033[37m         <path-to-csv>       CSV with patient_id and bamFile columns (for CYP2D6)
        \033[37m
        """
    } else {

        if (params.stepmode && params.exec == "pgx") { OncoPantherPgxOutput() }

        // Step 1: Preprocess VCF for PharmCAT
        PharmcatPreprocess(vcfChannel, pgxRefGenome)

        // Step 1b: CYP2D6 Star Allele Calling (Cyrius) — if enabled and BAMs available
        if (params.cyp2d6) {
            CYP2D6Call(bamChannel)

            // Join preprocessed VCF with Cyrius outside calls by patient_id
            pharmcatInput = PharmcatPreprocess.out.preprocessedVcf
                .join(CYP2D6Call.out.outsideCalls)
                // shape: [patient_id, preprocessedVcf, outsideCalls]
        } else {
            // No CYP2D6 calling — use dummy outside calls placeholder
            pharmcatInput = PharmcatPreprocess.out.preprocessedVcf
                .map { patient_id, vcf ->
                    tuple(patient_id, vcf, file("NO_OUTSIDE_CALLS"))
                }
        }

        // Step 2: Run PharmCAT Analysis (with or without CYP2D6 outside calls)
        PharmcatAnalysis(pharmcatInput)

        // Step 3: Generate PGx PDF Report (if reporting metadata is available)
        if (params.metaPatients && params.metaYaml && params.oncopantherLogo) {

            // Key metadata by SampleID to match with PharmCAT patient_id outputs
            metaKeyed = metaPipeExecYaml
                .map { metadata, vcFile, logo, yamlMap ->
                    tuple(metadata.SampleID, metadata, vcFile, logo, yamlMap)
                }

            // Key PharmCAT outputs by patient_id (position 0) for joining
            pharmcatOutputs = PharmcatAnalysis.out.reportJson
                .join(PharmcatAnalysis.out.matchJson)
                .join(PharmcatAnalysis.out.phenotypeJson)
                // shape: [patient_id, reportJson, matchJson, phenotypeJson]

            // Join metadata with PharmCAT outputs on patient_id/SampleID
            pgxReportInput = metaKeyed
                .join(pharmcatOutputs)
                .map { sampleId, metadata, vcFile, logo, yamlMap, reportJson, matchJson, phenotypeJson ->
                    tuple(metadata, vcFile, logo, yamlMap, reportJson, matchJson, phenotypeJson)
                }

            GeneratePgxReport(pgxReportInput)
        }
    }

    emit:
    preprocessedVcf = PharmcatPreprocess.out.preprocessedVcf
    missingPgxVars  = PharmcatPreprocess.out.missingPgxVars
    matchJson       = PharmcatAnalysis.out.matchJson
    phenotypeJson   = PharmcatAnalysis.out.phenotypeJson
    reportHtml      = PharmcatAnalysis.out.reportHtml
    reportJson      = PharmcatAnalysis.out.reportJson
}
