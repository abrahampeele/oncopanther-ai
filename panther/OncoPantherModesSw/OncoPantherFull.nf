#!/usr/bin/env nextflow

include { FullModeOutput 		} from '../.logos' 
include { FullModeBqsrOutput 	} from '../.logos'  

// Subworkflows
include { INDEXING_REF_GENOME 	} from '../subworkflows/indexingRefGenome'
include { ALIGN_TO_REF_GENOME 	} from '../subworkflows/mapping'
include { BASE_QU_SCO_RECA 		} from '../subworkflows/bqsr'
include { CALL_VARIANT_GATK 	} from '../subworkflows/variantcalling/gatk-hc'
include { CALL_VARIANT_DEEPVARIANT 	} from '../subworkflows/variantcalling/deepvariant'
include { VepAnnotation 		} from '../modules/07.1_VepAnnotate.nf'
include { ACMG_CLASSIFY 		} from '../subworkflows/annotations/acmg/main.nf'
include { PGX_ANALYSIS 			} from '../subworkflows/pgx'

workflow OncoPantherFullSw {
    take:
    RefGenChannel
    ReadsToBeAligned
    Target
    KnownSite1
    KnownSite2
    AddRSID
    PgxRefGenome
    metaPipeExecYaml


    main: 
	if ( params.input && ( params.reference || params.igenome ) && !params.caller ) {    
		if (params.bqsr) {
			FullModeBqsrOutput()
			INDEXING_REF_GENOME(RefGenChannel)

		    ALIGN_TO_REF_GENOME(
		        INDEXING_REF_GENOME.out.reference_fasta,
		        INDEXING_REF_GENOME.out.combinedIdx.collect(),
		        ReadsToBeAligned
		    ) 
		    
		    BASE_QU_SCO_RECA(
		        INDEXING_REF_GENOME.out.reference_fasta,
		        INDEXING_REF_GENOME.out.gatkDict,
		        INDEXING_REF_GENOME.out.samtoolsIndex,
		        ALIGN_TO_REF_GENOME.out.bamWithIdx,
		        KnownSite1,
		        KnownSite2
		    )
		    
		    CALL_VARIANT_GATK(
		        INDEXING_REF_GENOME.out.reference_fasta,
		        INDEXING_REF_GENOME.out.gatkDict,
		        INDEXING_REF_GENOME.out.samtoolsIndex,
		        BASE_QU_SCO_RECA.out.reaclBamWithIdx,
		        Target,
		        AddRSID
		    )

		    if (params.acmg) {
		        // VEP annotate first, then ACMG classify on VEP output
		        VepAnnotation(
		            CALL_VARIANT_GATK.out.CallVariantvcf,
		            INDEXING_REF_GENOME.out.reference_fasta,
		            INDEXING_REF_GENOME.out.samtoolsIndex,
		            params.cachedir,
		            params.species ?: 'homo_sapiens',
		            params.assembly ?: 'GRCh38',
		            params.cachetype ?: '',
		            params.cacheversion ?: ''
		        )
		        ACMG_CLASSIFY(
		            VepAnnotation.out.vcf
		                .map { vcf -> tuple(vcf.simpleName.replaceAll('_vep.*',''), vcf, file("${vcf}.tbi")) }
		        )
		    }
		    if (params.pgx) {
		        PGX_ANALYSIS(CALL_VARIANT_GATK.out.CallVariantvcf, PgxRefGenome, metaPipeExecYaml, BASE_QU_SCO_RECA.out.reaclBamWithIdx)
		    }

		} else {
			FullModeOutput()
			INDEXING_REF_GENOME(RefGenChannel)

		    ALIGN_TO_REF_GENOME(
		        INDEXING_REF_GENOME.out.reference_fasta,
		        INDEXING_REF_GENOME.out.combinedIdx.collect(),
		        ReadsToBeAligned
		    )

		    CALL_VARIANT_GATK(
		        INDEXING_REF_GENOME.out.reference_fasta,
		        INDEXING_REF_GENOME.out.gatkDict,
		        INDEXING_REF_GENOME.out.samtoolsIndex,
		        ALIGN_TO_REF_GENOME.out.bamWithIdx,
		        Target,
		        AddRSID
		    )

		    if (params.acmg) {
		        VepAnnotation(
		            CALL_VARIANT_GATK.out.CallVariantvcf,
		            INDEXING_REF_GENOME.out.reference_fasta,
		            INDEXING_REF_GENOME.out.samtoolsIndex,
		            params.cachedir,
		            params.species ?: 'homo_sapiens',
		            params.assembly ?: 'GRCh38',
		            params.cachetype ?: '',
		            params.cacheversion ?: ''
		        )
		        ACMG_CLASSIFY(
		            VepAnnotation.out.vcf
		                .map { vcf -> tuple(vcf.simpleName.replaceAll('_vep.*',''), vcf, file("${vcf}.tbi")) }
		        )
		    }
		    if (params.pgx) {
		        PGX_ANALYSIS(CALL_VARIANT_GATK.out.CallVariantvcf, PgxRefGenome, metaPipeExecYaml, ALIGN_TO_REF_GENOME.out.bamWithIdx)
		    }
		}
	} else if ( params.input && ( params.reference || params.igenome ) && params.caller	== "deepvariant" && params.modelType    != null ) {
		if (params.bqsr) {
			FullModeBqsrOutput()
			INDEXING_REF_GENOME(RefGenChannel)

		    ALIGN_TO_REF_GENOME(
		        INDEXING_REF_GENOME.out.reference_fasta,
		        INDEXING_REF_GENOME.out.combinedIdx.collect(),
		        ReadsToBeAligned
		    ) 
		    
		    BASE_QU_SCO_RECA(
		        INDEXING_REF_GENOME.out.reference_fasta,
		        INDEXING_REF_GENOME.out.gatkDict,
		        INDEXING_REF_GENOME.out.samtoolsIndex,
		        ALIGN_TO_REF_GENOME.out.bamWithIdx,
		        KnownSite1,
		        KnownSite2
		    )
		    
		    CALL_VARIANT_DEEPVARIANT(
		        INDEXING_REF_GENOME.out.reference_fasta,
		        INDEXING_REF_GENOME.out.gatkDict,
		        INDEXING_REF_GENOME.out.samtoolsIndex,
		        BASE_QU_SCO_RECA.out.reaclBamWithIdx
		    )

		    if (params.pgx) {
		        PGX_ANALYSIS(CALL_VARIANT_DEEPVARIANT.out.CallVariantvcf, PgxRefGenome, metaPipeExecYaml, BASE_QU_SCO_RECA.out.reaclBamWithIdx)
		    }

		} else {
			FullModeOutput()
			INDEXING_REF_GENOME(RefGenChannel)

		    ALIGN_TO_REF_GENOME(
		        INDEXING_REF_GENOME.out.reference_fasta,
		        INDEXING_REF_GENOME.out.combinedIdx.collect(),
		        ReadsToBeAligned
		    )

		    CALL_VARIANT_DEEPVARIANT(
		        INDEXING_REF_GENOME.out.reference_fasta,
		        INDEXING_REF_GENOME.out.gatkDict,
		        INDEXING_REF_GENOME.out.samtoolsIndex,
		        ALIGN_TO_REF_GENOME.out.bamWithIdx
		    )

		    if (params.pgx) {
		        PGX_ANALYSIS(CALL_VARIANT_DEEPVARIANT.out.CallVariantvcf, PgxRefGenome, metaPipeExecYaml, ALIGN_TO_REF_GENOME.out.bamWithIdx)
		    }
		}
	} else {
	FullModeBqsrOutput()
	print("\033[31m Please specify valid parameters:\n" )
	print(" --input <path-to-csv> \n"			)
	print(" --reference <path-to-reference>\n"	)
	print(" --------------------------------------------------------------------------------------------\n"	)
	print(" If igenomes are preferred please use --igenome <value> instead of --reference : \n"	)
	print(" --------------------------------------------------------------------------------------------\n"	)
	print(" If Base quality score recalibration is preferred please add : \n"	)
	print(" --bqsr >>> Check help menu for full details \n"	)
	print(" --------------------------------------------------------------------------------------------\n"	)
	print(" If depvariant is preferred as a variant caller please add : \n"	)
	print(" --caller deepvariant --modelType <WGS|WES|PACBIO|ONT_R104|HYBRID_PACBIO_ILLUMINA|MASSEQ> \n"	)
	print(" --------------------------------------------------------------------------------------------\n"	)
	print(" optional : --mode cohort  \n" 																  	)  
	print(" --------------------------------------------------------------------------------------------\n"	)
	print(" For more information:\n"                                    )	
    print("   >>  View the help menu: nextflow main.nf --help\n"		)
	print("   >>  Check parameters: nextflow main.nf --params\n\033[37m")

	}
}
