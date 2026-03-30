#!/usr/bin/env nextflow

nextflow.enable.dsl = 2

// params 

// Interactive Design while Running OncoPanther

include {OncoPantherWelcome	}	from './.logos'
include {OncoPantherParams	}	from './.logos'
include {OncoPantherHelp	} 	from './.logos' 

	       			             	 	
// channels 
  // prepare required csv from an intial csv
  PrepareCsv 		= params.basedon	? Channel.fromPath(params.basedon, checkIfExists: true)   			: Channel.empty()   	
 
  // Raw Reads to quality check 
  RawReads 		= params.rawreads 	? Channel.fromPath(params.rawreads, checkIfExists: true)       	
	       			             	 	  .splitCsv(header: true)  
       	       	                     		           .map { row -> tuple(row.patient_id, file(row.R1), file(row.R2)) }	: Channel.empty() 
       	       
  // Raw Reads to be trimmed based on required features  : MINLEN , LEADING, TRAILING, SLIDINGWINDOW
       	
  ReadsToBeTrimmed	= params.tobetrimmed 	? Channel.fromPath(params.tobetrimmed, checkIfExists: false)       	
	       						  .splitCsv(header: true)  
	       						   .map { row -> tuple(row.patient_id,
       		      					    file(row.R1), 
       		      				   	     file(row.R2), 
       		      				              row.MINLEN, 	
       		         				       row.LEADING,
       		         			 	        row.TRAILING,  
	           				         	 row.SLIDINGWINDOW ) }
	           				         	 .toSortedList { a, b -> a[0] <=> b[0] }   	 
                                      		   	          .flatMap { it }						: Channel.empty()
  // reference

  inputFileChannel 	= params.input ?: params.tobealigned
    // Trimmed reads      	       
  ReadsToBeAligned	= inputFileChannel	? Channel.fromPath(inputFileChannel, checkIfExists: false)       	
	       					 	  .splitCsv(header: true)  
       	      				          	   .map { row -> tuple(row.patient_id, file(row.R1), file(row.R2)) }
                               	     		  	    .toSortedList { a, b -> a[0] <=> b[0] }   	 
                                      		   	     .flatMap { it } 							: Channel.empty()
  // reference
  referFileChannel 	= params.reference ?: params.igenome
  RefGenChannel		= referFileChannel	? Channel.fromPath(referFileChannel).first()					: Channel.empty()
  
  // BamFiles channel
    // used for base recalibration
    MappedReads 	= params.bam 		? Channel.fromPath(params.bam, checkIfExists: false)
                                   			  .splitCsv(header: true)
							   .map { row ->
							       def bam       = file(row.BamFile)
							       def indexPath = bam.toString() + '.bai'
							       def indexFile = file(indexPath)

								  if (!indexFile.exists()) {
								      log.warn "Index file missing for BAM: ${bam}. Expected: ${indexPath}"
								      indexFile = null
								      }
							       tuple(row.patient_id, bam, indexFile)
							       
							   }.toSortedList { a, b -> a[0] <=> b[0] }   	 
                                      		   	    .flatMap { it } 							: Channel.empty()
    // used for variant calling
    ToVarCall		= params.tovarcall      ? Channel.fromPath(params.tovarcall, checkIfExists: false)
                                   			  .splitCsv(header: true)
							   .map { row ->
							       def bam       = file(row.BamFile)
							       def indexPath = bam.toString() + '.bai'
							       def indexFile = file(indexPath)

								  if (!indexFile.exists()) {
								      log.warn "Index file missing for BAM: ${bam}. Expected: ${indexPath}"
								      indexFile = null
								      }
							       tuple(row.patient_id, bam, indexFile)
							   }.toSortedList { a, b -> a[0] <=> b[0] }   	 
                                      		   	    .flatMap { it } 							: Channel.empty()
    						
  // target bed file to extract coverage 
  Target 		= params.bedtarget	? Channel.fromPath(params.bedtarget, checkIfExists: true).first()	: Channel.value(file("NO_FILE"))
	
  // knwon file 1 channel for BQSR    

  KnownSite1		= params.knownsite1	? Channel.fromPath(params.knownsite1, checkIfExists: false)
							   .map { vcfile ->
							      def id = vcfile.baseName
							      def tbi = vcfile.toString() + '.tbi'
							      def idx = vcfile.toString() + '.idx'
							      def indexFile = file(tbi).exists() ? file(tbi) : file(idx)
							      tuple(id, vcfile, indexFile)
							   }.first()   								: Channel.empty() 
       			         
  // knwon file 2 channel for BQSR       
         
  KnownSite2 		= params.knownsite2 	? Channel.fromPath(params.knownsite2, checkIfExists: false)
							  .map { vcfile ->
							      def id = vcfile.baseName
							      def tbi = vcfile.toString() + '.tbi'
							      def idx = vcfile.toString() + '.idx'
							      def indexFile = file(tbi).exists() ? file(tbi) : file(idx)
							      tuple(id, vcfile, indexFile)
							   }.first()								: Channel.empty()
 // VCF for Bcftools annotation
 
  AddRSID 			= params.rsid 	? Channel.fromPath(params.rsid, checkIfExists: false)
							  .map { vcfile ->
							      def id = vcfile.baseName
							      def tbi = vcfile.toString() + '.tbi'
							      def idx = vcfile.toString() + '.idx'
							      def indexFile = file(tbi).exists() ? file(tbi) : file(idx)
							      tuple(id, vcfile, indexFile)
							   }.first()								: Channel.empty()

 // Indexes Channels 

    // Aligner Indexs Bwa mem2 
    AlignIdxRef = params.reference ? Channel.fromPath("${file(params.reference).getParent()}/*.{0123,amb,ann,bwt.2bit.64,pac,bwt,sa}", checkIfExists: false )	: Channel.empty()
   	
    //  Dictionary Indexs Bwa mem2 
    DictIdxRef		= params.reference ? Channel.fromPath("${file(params.reference).getParent()}/*.dict", checkIfExists: false)			      	: Channel.empty()
       	
    // SamtoolsIndex
    SamtIdxRef = params.reference ? Channel.fromPath("${file(params.reference).parent}/${file(params.reference).name}.{fai,gzi}",checkIfExists: false )       	: Channel.empty()

       		 
  // Vep Annotations Channels
    
 
    VepSpecies		= params.species	?: ''     	 
    Assembly		= params.assembly 	?: ''	 
    CacheType 		= params.cachetype	?: ''
    CacheDir 		= params.cachedir 	?: ''
    CacheVersion	= params.cacheversion 	?: ''
    
    CacheDirANN		= CacheDir		? Channel.fromPath(params.cachedir , checkIfExists: false).first()		: Channel.empty()
  
  // vcf channels
  
    VcfChannel      	= params.toannotate 	? Channel.fromPath(params.toannotate, checkIfExists: false)
    							  						  .splitCsv(header: true)  
       	      			       		 	   				   .map { row -> tuple(row.patient_id, file(row.vcFile) ) }		: Channel.empty() 	 

    FilterChannel 		= params.tofilter 		? Channel.fromPath(params.tofilter, checkIfExists: false)
    							  						  .splitCsv(header: true)
    							  						   .map { row ->
    							  						   		def vcFile = file(row.vcFile)
    							  						   		def tbi = file("${vcFile}.tbi")
    							  						   		def idx = file("${vcFile}.idx")
    							  						   		def indexFile = tbi.exists() ? tbi : idx.exists() ? idx : null
    							  						   		tuple(row.patient_id, vcFile, indexFile) } 				: Channel.empty()

  // PGx Channels
    PgxVcfChannel		= params.pgxVcf			? Channel.fromPath(params.pgxVcf, checkIfExists: false)
    							  .splitCsv(header: true)
    							   .map { row ->
    							   	def vcFile = file(row.vcFile)
    							   	def tbi = file("${vcFile}.tbi")
    							   	def idx = file("${vcFile}.idx")
    							   	def indexFile = tbi.exists() ? tbi : idx.exists() ? idx : null
    							   	tuple(row.patient_id, vcFile, indexFile) }				: Channel.empty()

    PgxRefGenome		= params.pgxRefGenome		? Channel.fromPath(params.pgxRefGenome, checkIfExists: true).first()
    							  								: Channel.value(file("NO_FILE"))

  // PGx BAM Channel for CYP2D6 calling (Cyrius)
    PgxBamChannel		= params.pgxBam			? Channel.fromPath(params.pgxBam, checkIfExists: false)
    							  .splitCsv(header: true)
    							   .map { row ->
    							   	def bamFile = file(row.bamFile)
    							   	def baiFile = file("${bamFile}.bai")
    							   	tuple(row.patient_id, bamFile, baiFile) }			: Channel.empty()

  // Reporting
     	// Function to parse YAML file
	import groovy.yaml.YamlSlurper

 	def parseYamlFile(yamlFile) { new YamlSlurper().parse(yamlFile) }
    // OncoPanther Logo Channel
    oncoPantherLogoCh 	= params.oncopantherLogo	? Channel.fromPath(params.oncopantherLogo)						: Channel.empty()
    // Patients Metadata with annotated Vcf paths Combined to Logo Channel
    metaPatiLogCh 	= params.metaPatients	? Channel.fromPath(params.metaPatients)
							  .splitCsv(header: true)
							   .map { row ->
							    	metaPatients = [
								    Identifier: row.Identifier,
								    SampleID: row.SampleID,
								    Sex: row.Gender,
								    Dob: row.Dob,
								    Ethnicity: row.Ethnicity,
								    Diagnosis: row.Diagnosis,
							    	]
							    	[metaPatients, file(row.vcFile)]
								}.combine(oncoPantherLogoCh)					: Channel.empty()

    // Pipeline Executions step with Physician Metadata Parsing
    pipeExecYamlCh 	= params.metaYaml	? Channel.fromPath(params.metaYaml)
        						  .map { file -> parseYamlFile(file) }					: Channel.empty()
 

    // Combine both channels ( metaPatiLogCh with  pipeExecYamlCh ) 
    // Combine both channels ( metaPatiLogCh with  pipeExecYamlCh ) 
    metaPipeExecYaml = params.metaPatients && params.metaYaml ? metaPatiLogCh.combine(pipeExecYamlCh)
                        						      .map { metaPatients, vcFile, oncoPantherLogo, pipeExecYamlCh ->
										    [metaPatients, vcFile, oncoPantherLogo, pipeExecYamlCh]
										}						: Channel.empty()
        
// subworkflows

include { OncoPantherSteps 		} from './OncoPantherModesSw/OncoPantherSteps.nf'
include { OncoPantherFullSw 	} from './OncoPantherModesSw/OncoPantherFull.nf'

// Publication validation modules (--validation / --benchmark)
include { GIAB_DOWNLOAD; INSTALL_HAPY; HAPY_BENCHMARK; BENCHMARK_AGGREGATE } from './modules/11.0_GiabValidation.nf'
include { RUNTIME_BENCHMARK_LINEAR; RUNTIME_BENCHMARK_SCATTER; BENCHMARK_PLOT } from './modules/11.1_RuntimeBenchmark.nf'

// Channels for validation modes
// FIX: use dedicated --valvcf param (separate from --tovarcall which expects BamFile column)
//      avoids file(null) crash when validation CSV has VcfFile column not BamFile column
ValidationVcf   = params.validation && params.valvcf ? Channel.fromPath(params.valvcf, checkIfExists: false)
                      .splitCsv(header: true)
                      .map { row -> tuple(row.patient_id,
                                         file(row.VcfFile),
                                         file(row.VcfFile + '.tbi')) }             : Channel.empty()

params.params = null
params.help   = null
params.valvcf = params.valvcf ?: null   // dedicated VCF CSV param for --validation mode
workflow {

    if (params.validation) {
        // ── Module 11.0: GIAB Benchmark ─────────────────────────────────────
        // Usage: nextflow run main.nf --validation true --valvcf vcf.csv --reference ref.fa
        giab_ids = Channel.from(params.giab_samples ?: ["HG002"])
        GIAB_DOWNLOAD(giab_ids)
        INSTALL_HAPY( RefGenChannel )   // builds hap.py + rtgtools SDF from reference
        // Cross-join: each query VCF benchmarked against each GIAB truth set
        query_x_truth = ValidationVcf.combine(GIAB_DOWNLOAD.out.truth_set)
        HAPY_BENCHMARK( query_x_truth, INSTALL_HAPY.out.flag, INSTALL_HAPY.out.sdf, RefGenChannel )
        BENCHMARK_AGGREGATE(
            HAPY_BENCHMARK.out.benchmark_results
                .map { sid, gid, summary, extended, html -> summary }
                .collect()
        )

    } else if (params.benchmark) {
        // ── Module 11.1: Runtime Benchmark ──────────────────────────────────
        // Usage: nextflow run main.nf --benchmark true --tovarcall bam.csv --reference ref.fa
        ref_fai  = Channel.fromPath(params.reference + '.fai').first()
        ref_dict = Channel.fromPath(params.reference.replaceAll(/\.(fa|fasta|fna)$/, '') + '.dict').first()
        RUNTIME_BENCHMARK_LINEAR( ToVarCall, RefGenChannel, ref_fai, ref_dict )
        RUNTIME_BENCHMARK_SCATTER( ToVarCall, RefGenChannel, ref_fai, ref_dict )
        BENCHMARK_PLOT(
            RUNTIME_BENCHMARK_LINEAR.out.linear_timing
                .mix(RUNTIME_BENCHMARK_SCATTER.out.scatter_timing)
                .map { sid, timing, cpu -> [timing, cpu] }
                .flatten()
                .collect()
        )

    } else if (params.fullmode) {

	OncoPantherFullSw(   RefGenChannel
		 	,ReadsToBeAligned
		 	,Target
		 	,KnownSite1
		 	,KnownSite2
		 	,AddRSID
		 	,PgxRefGenome
		 	,metaPipeExecYaml
		 	)
  } else if (params.stepmode){

          OncoPantherSteps(  PrepareCsv
			,RawReads
		 	,ReadsToBeTrimmed
		 	,RefGenChannel
		 	,AlignIdxRef
		 	,ReadsToBeAligned
		 	,Target
		 	,DictIdxRef
		 	,SamtIdxRef
		 	,MappedReads
		 	,KnownSite1
		 	,KnownSite2
		 	,AddRSID
		 	,ToVarCall
		 	,VepSpecies
		 	,Assembly
		 	,CacheType
		 	,CacheDir
		 	,CacheVersion
		 	,VcfChannel
		 	,FilterChannel
		 	,CacheDirANN
		 	,metaPipeExecYaml
		 	,PgxVcfChannel
		 	,PgxRefGenome
		 	,PgxBamChannel)
    } else if (params.params){
	OncoPantherParams()
    } else if (params.help) {
       OncoPantherHelp()
    } else {
      OncoPantherWelcome()
    }
   
}
   	 


 
