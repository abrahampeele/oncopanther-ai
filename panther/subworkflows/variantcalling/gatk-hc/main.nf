// Variant Calling subworkflow 

include { OncoPantherWelcome	} from '../../../.logos'
include { OncoPantherVarCallOutput	} from '../../../.logos'
	
 
include { CallVariant         } from '../../../modules/06.0_VariantSNPcall-HC.nf' 
include { ScatterCallVariant  } from '../../../modules/06.0_VariantSNPcall-HC.nf'
include { GatherVcfs          } from '../../../modules/06.0_VariantSNPcall-HC.nf'
include { CreateGVCF      } from '../../../modules/06.0_VariantSNPcall-HC.nf'  
include { CombineGvcfs    } from '../../../modules/06.0_VariantSNPcall-HC.nf'  
include { GenotypeGvcfs   } from '../../../modules/06.0_VariantSNPcall-HC.nf' 
include { GenerateStats   } from '../../../modules/06.2_VarMetrics.nf'
include { RsAnnotation    } from '../../../modules/06.3_VarAnnot_bcftools.nf' 

workflow CALL_VARIANT_GATK {

    take:
    ref_gen_channel
    dictREF
    samidxREF
    BamToVarCall
    bedtarget
    AnnotRefVCF
 
    main:
    if (params.stepmode && params.exec == "callvar" ) { OncoPantherVarCallOutput() }

    // Determine if we are using local reference or igenome fasta retrieving
    def referFileChannel = params.reference ?: params.igenome

    // Output channel — captures VCF from whichever mode runs (single-sample or cohort)
    def vcf_out_ch = Channel.empty()

    if  (params.mode 		== null &&
   	 referFileChannel 	!= null ){

	// ── Scatter: one GATK HC job per chromosome ──────────────────────────────
	def grch38Chroms = Channel.from([
	    'chr1','chr2','chr3','chr4','chr5','chr6','chr7','chr8','chr9',
	    'chr10','chr11','chr12','chr13','chr14','chr15','chr16','chr17',
	    'chr18','chr19','chr20','chr21','chr22','chrX','chrY','chrM'
	])

	// Combine each BAM with every chromosome → parallel scatter jobs
	def scatteredInput = BamToVarCall.combine(grch38Chroms)

	ScatterCallVariant(
	    ref_gen_channel,
	    dictREF.collect(),
	    samidxREF.collect(),
	    scatteredInput
	)

	// ── Gather: merge per-chromosome VCFs back per patient ────────────────────
	def gatheredVcfs = ScatterCallVariant.out.scatterVcf.groupTuple()
	GatherVcfs(gatheredVcfs)

	///// Metrics Extracting from merged vcf
	GenerateStats(GatherVcfs.out.CallVariantvcf)
        if ( params.rsid ) {
            RsAnnotation(GatherVcfs.out.CallVariantvcf, AnnotRefVCF )
        }
        vcf_out_ch = vcf_out_ch.mix(GatherVcfs.out.CallVariantvcf)

    } else if ( referFileChannel 	!= null &&
		params.mode 		== 'cohort' ){	// generate vcf for all inputs

	CreateGVCF	( ref_gen_channel
	                 ,dictREF.collect()
	                 ,samidxREF.collect()
	                 ,BamToVarCall
	                 ,bedtarget)

	CombineGvcfs	( ref_gen_channel,
			  dictREF.collect(),
			  samidxREF.collect(),
			  CreateGVCF.out.g_vcf_Recal.map { id, gvcf, idx -> tuple("cohort", gvcf, idx) }.groupTuple() )

	GenotypeGvcfs 	( ref_gen_channel,dictREF.collect(),samidxREF.collect(),CombineGvcfs.out.CohortVcf )

	GenerateStats	( GenotypeGvcfs.out )

	if ( params.rsid ) {
            RsAnnotation(GenotypeGvcfs.out, AnnotRefVCF )
        }
        vcf_out_ch = vcf_out_ch.mix(GenotypeGvcfs.out)

    }  else {
	print("\033[31m Error: Invalid or missing parameters.\n" )
	print(" Please specify valid parameters:\n"              )
	print(" --reference option (--reference reference ) \n" )
	print(" --tovarcall option (--tovarcall CSVs/5_samplesheetReclibFiles.csv )\n "  )
	print(" --mode cohort  ( Default : null --> will generate a single vcfs )\n "    )
        print(" --caller deepvariant ( Default : no caller --> variant calling with gatk )\n " )
        print(" ---------------------------------------------------------------------------\n"  )
        print(" For more information:\n"                                        )
        print("   >>  View the help menu: nextflow main.nf --help\n"            )
        print("   >>  Check parameters: nextflow main.nf --params\n\033[37m"    )
    }

    emit:
    CallVariantvcf = vcf_out_ch     // tuple val(patient_id), path(vcf), path(vcfIdx)
}


