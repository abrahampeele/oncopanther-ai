#!/bin/bash
echo "=== RAM ==="
free -h

echo ""
echo "=== Disk space ==="
df -h /home/crak/
df -h /mnt/c/ 2>/dev/null | head -5

echo ""
echo "=== CPU cores ==="
nproc

echo ""
echo "=== WSL2 memory limit ==="
cat /proc/meminfo | grep -E "MemTotal|MemAvailable|SwapTotal"

echo ""
echo "=== BWA vs BWA-MEM2 RAM requirement note ==="
echo "BWA (classic)   index: ~5-6 GB RAM  -- OK for 7.4GB system"
echo "BWA-MEM2        index: ~28 GB RAM   -- TOO MUCH for 7.4GB system"
echo "Current aligner in params.json: bwamem2"
