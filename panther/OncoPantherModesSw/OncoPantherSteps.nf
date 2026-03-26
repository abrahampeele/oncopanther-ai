#!/usr/bin/env nextflow

nextflow.enable.dsl = 2

// params 

// Interactive Design while Running OncoPanther

include {OncoPantherWelcome		}    from '../.logos' 
include {OncoPantherSmExec		}    from '../.logos'
include {OncoPantherParams		}    from '../.logos' 
include {OncoPantherVersion		}    from '../.logos' 
include {OncoPantherHelp		}    from '../.logos' 
include {OncoPantherError		}    from '../.logos' 
include {OncoPantherAnnotateHelp	}    from '../.logos' 

// subworkflows 
include { GENERATE_CSVS		} from '../subworkflows/generateCSV'
include { QC_RAW_READS		} from '../subworkflows/rawQualCtrl'
include { TRIM_READS		} from '../subworkflows/trimming'
include { INDEXING_REF_GENOME	} from '../subworkflows/indexingRefGenome'
include { ALIGN_TO_REF_GENOME	} from '../subworkflows/mapping'
include { BASE_QU_SCO_RECA	} from '../subworkflows/bqsr'
include { CALL_VARIANT_GATK	} from '../subworkflows/variantcalling/gatk-hc'
include { CALL_VARIANT_DEEPVARIANT	} from '../subworkflows/variantcalling/deepvariant'
include { FILTER_VARIANT	} from '../subworkflows/variantfilter'
include { VEP_CACHE			} from '../subworkflows/annotations/vep/vepcache'
include { VEP_ANNOTATE		} from '../subworkflows/annotations/vep/vepannotate'
include { ACMG_CLASSIFY		} from '../subworkflows/annotations/acmg/main.nf'
include { REPORTING			} from '../subworkflows/reporting/main.nf'
include { PGX_ANALYSIS			} from '../subworkflows/pgx'


workflow OncoPantherSteps {

    take: 
    PrepareCsv
    RawReads
    ReadsToBeTrimmed
    RefGenChannel
    AlignIdxRef
    ReadsToBeAligned
    Target
    DictIdxRef
    SamtIdxRef
    MappedReads
    KnownSite1
    KnownSite2
    AddRSID
    ToVarCall
    VepSpecies 
    Assembly
    CacheType
    CacheDir
    CacheVersion
    VcfChannel
    FilterChannel
    CacheDirANN
    metaPipeExecYaml
    PgxVcfChannel
    PgxRefGenome
    PgxBamChannel

    main:
    
    params.exec = null  // Default to 'none' if not provided
  
    if (params.exec == null ){
    
    OncoPantherWelcome() 
    OncoPantherSmExec()

    GENERATE_CSVS(PrepareCsv)
  
    } else if (params.exec == 'rawqc') {    // check quality of raw reads
 
    QC_RAW_READS(RawReads)  
        
    } else if (params.exec == 'trim') {        // trim reads

    TRIM_READS(ReadsToBeTrimmed)  
    
    } else if (params.exec == 'refidx') {    // generate index for reference genome    

    INDEXING_REF_GENOME(RefGenChannel) 
 
    } else if (params.exec == 'align') {    // align reads to reference

    ALIGN_TO_REF_GENOME(RefGenChannel,AlignIdxRef,ReadsToBeAligned) 
     
    } else if (params.exec == 'bqsr') {
           
    BASE_QU_SCO_RECA(RefGenChannel,DictIdxRef,SamtIdxRef,MappedReads,KnownSite1,KnownSite2 )
               
    } else if (params.exec == 'callvar' && !params.caller ) {    // Call snp
              
    CALL_VARIANT_GATK(RefGenChannel,DictIdxRef,SamtIdxRef,ToVarCall,Target,AddRSID) 
          
    } else if (params.exec == 'callvar' && params.caller == 'deepvariant') {    // Call snp
              
    CALL_VARIANT_DEEPVARIANT(RefGenChannel,DictIdxRef,SamtIdxRef,ToVarCall) 
          
    } else if (params.exec == 'filter') {
    
    FILTER_VARIANT(FilterChannel)
    
    } else if ( params.exec == 'annotate' ) {

    OncoPantherAnnotateHelp()
               
    } else if ( params.exec == 'vepcache' ) {
              
    VEP_CACHE(VepSpecies,Assembly,CacheType,CacheDir,CacheVersion)
               
    } else if ( params.exec == 'vepannotate' ) {

    VEP_ANNOTATE(VcfChannel,RefGenChannel,SamtIdxRef,CacheDirANN,VepSpecies,Assembly,CacheType,CacheVersion)

    } else if ( params.exec == 'acmg' ) {
    // ACMG/AMP 2015 variant classification from VEP-annotated VCFs
    // Usage: nextflow run main.nf --stepmode --exec acmg --toannotate CSVs/6_samplesheetvcfFiles.csv --acmg
    if (!params.toannotate) error "[OncoPanther] --toannotate CSV required for --exec acmg"
    def acmgVcfCh = Channel
        .fromPath(params.toannotate)
        .splitCsv(header:true)
        .map { row -> tuple(row.patient_id, file(row.vcFile), file(row.vcFile + ".tbi")) }
    ACMG_CLASSIFY(acmgVcfCh)

    } else if (params.exec == 'reporting') {

    REPORTING(metaPipeExecYaml)

    } else if (params.exec == 'pgx') {

    PGX_ANALYSIS(PgxVcfChannel, PgxRefGenome, metaPipeExecYaml, PgxBamChannel)

    } else if ( params.exec == 'help'){
             
    OncoPantherHelp()
            
    } else if ( params.exec == 'params' ) {
                     
    OncoPantherParams()
                
    } else if ( params.exec == 'version' ) {
                
    OncoPantherVersion()

    } else { OncoPantherError() }
   
 }
       
