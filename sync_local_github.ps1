# Script de synchronisation automatique locale OneDrive <-> GitHub
# D:\OneDrive\AI-Tools\PROJETS\1_CHAINES-YOUTUBE_suivi\YT_PursuingAi\sync_local_github.ps1

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "🔄 Synchronisation de YT_PursuingAi avec GitHub..." -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan

Set-Location -Path $PSScriptRoot

try {
    git fetch origin main
    $status = git status -uno
    if ($status -match "Your branch is behind") {
        Write-Host "📥 Nouvelles vidéos et fiches détectées sur GitHub ! Récupération en cours..." -ForegroundColor Green
        git pull origin main
        Write-Host "✅ Synchronisation locale OneDrive terminée avec succès." -ForegroundColor Green
    } else {
        Write-Host "✨ Le dossier local OneDrive est déjà parfaitement à jour avec GitHub." -ForegroundColor Green
    }
} catch {
    Write-Host "❌ Erreur de synchronisation Git : $_" -ForegroundColor Red
}
