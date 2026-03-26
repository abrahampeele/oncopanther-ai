#!/bin/bash
source /home/crak/miniconda3/etc/profile.d/conda.sh
conda activate base
export PATH=/home/crak/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

CYRIUS_DIR=/home/crak/tools/Cyrius

echo "=== Cloning Cyrius v1.1.1 ==="
mkdir -p /home/crak/tools
if [ -d "$CYRIUS_DIR" ]; then
    echo "Already cloned — pulling latest"
    cd $CYRIUS_DIR && git pull
else
    git clone --depth 1 --branch v1.1.1 https://github.com/Illumina/Cyrius.git $CYRIUS_DIR
fi

echo ""
echo "=== Cyrius repo contents ==="
ls -la $CYRIUS_DIR/

echo ""
echo "=== Installing requirements ==="
pip install -r $CYRIUS_DIR/requirements.txt 2>&1 | tail -10

echo ""
echo "=== Creating cyrius wrapper in PATH ==="
cat > /home/crak/miniconda3/bin/cyrius << 'WRAPPER'
#!/bin/bash
exec python3 /home/crak/tools/Cyrius/star_caller.py "$@"
WRAPPER
chmod +x /home/crak/miniconda3/bin/cyrius

echo ""
echo "=== Verifying ==="
which cyrius
cyrius --help 2>&1 | head -15
