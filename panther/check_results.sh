#!/bin/bash
source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base
export PATH=/usr/lib/jvm/java-17-openjdk-amd64/bin:/home/crak/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

OUTDIR=/mnt/c/Users/drkat/OneDrive/Desktop/oncopanther-pgx/oncopanther-pgx/panther/outdir

echo "=== Output files ==="
find $OUTDIR -name "*NA12878*" -o -name "*12878*" 2>/dev/null | sort

echo ""
echo "=== PharmCAT phenotype JSON (gene calls) ==="
cat $OUTDIR/PGx/pharmcat/NA12878.phenotype.json 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
genes = data.get('genes', {})
print(f'Total genes analyzed: {len(genes)}')
print()
called = []
unknown = []
for gene, info in sorted(genes.items()):
    diplotypes = info.get('sourceDiplotypes', []) or info.get('diplotypes', [])
    if diplotypes:
        for d in diplotypes:
            label = d.get('label', 'N/A')
            pheno = d.get('phenotype', 'N/A')
            if 'Unknown' not in label:
                called.append((gene, label, pheno))
            else:
                unknown.append((gene, label))
    else:
        unknown.append((gene, 'No diplotypes'))

print('=== CALLED GENES ===')
for gene, label, pheno in called:
    print(f'  {gene}: {label} -> {pheno}')

print()
print(f'=== UNCALLED ({len(unknown)} genes) ===')
for gene, label in unknown:
    print(f'  {gene}: {label}')
"
