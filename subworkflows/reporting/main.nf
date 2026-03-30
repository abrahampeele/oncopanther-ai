// Variant Calling subworkflow 

include { OncoPantherWelcome	} from '../../.logos'
include { OncoPantherReporting	} from '../../.logos'
	
include { GenerateReports	} from '../../modules/08.0_Reporting.nf'
 
workflow REPORTING {

    take:
    patInfoVcfLogoMeta
    
    main:  
    if (params.oncopantherLogo 	&&
    	params.metaPatients &&
    	params.metaYaml )  {
	    
    	OncoPantherReporting()
    	GenerateReports(patInfoVcfLogoMeta)
 
    } else { 
   	OncoPantherWelcome() 
	print("\033[31m Please specify valid parameters:\n"			)
	print(" --metaPatients option (--metaPatients CSVs/7_metaPatients.csv ) \n"	)
	print(" --metaYaml option (--metaYaml CSVs/7_metaPatients.yml)\n "		)
    } 
}



 

 
	    
	    
	
