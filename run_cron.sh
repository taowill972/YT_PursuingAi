#!/bin/bash
set -e
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"
cd /root/YT_PursuingAi

echo "==========================================================" >> /var/log/yt_pursuingai.log
echo "🚀 [$(date -u +"%Y-%m-%d %H:%M:%S UTC")] Démarrage du batch 6h (Lot de 7 vidéos)" >> /var/log/yt_pursuingai.log
/usr/bin/python3 /root/YT_PursuingAi/batch_runner.py >> /var/log/yt_pursuingai.log 2>&1
echo "🏁 [$(date -u +"%Y-%m-%d %H:%M:%S UTC")] Fin du batch 6h" >> /var/log/yt_pursuingai.log
