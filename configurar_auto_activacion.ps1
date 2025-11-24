# Script para configurar la activación automática del entorno virtual
# Este script modifica el perfil de PowerShell para activar automáticamente el venv

$projectPath = "C:\Users\Soporte\Documents\Proyectos\ProyectoNewmont\ExtractorOCRv1"
$venvPath = Join-Path $projectPath "venv\Scripts\Activate.ps1"

# Obtener la ruta del perfil de PowerShell
$profilePath = $PROFILE.CurrentUserAllHosts

# Crear el directorio del perfil si no existe
$profileDir = Split-Path -Parent $profilePath
if (-not (Test-Path $profileDir)) {
    New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
    Write-Host "Directorio del perfil creado: $profileDir" -ForegroundColor Green
}

# Código a agregar al perfil
$autoActivationCode = @"

# Activación automática del entorno virtual para ExtractorOCRv1
`$extractorPath = "$projectPath"
if (`$PWD.Path -eq `$extractorPath -or `$PWD.Path.StartsWith(`$extractorPath + "\")) {
    `$venvActivate = Join-Path `$extractorPath "venv\Scripts\Activate.ps1"
    if (Test-Path `$venvActivate) {
        if (-not `$env:VIRTUAL_ENV) {
            Write-Host "`n[Activando entorno virtual de ExtractorOCRv1...]" -ForegroundColor Cyan
            & `$venvActivate
        }
    }
}
"@

# Verificar si el código ya existe en el perfil
$profileContent = ""
if (Test-Path $profilePath) {
    $profileContent = Get-Content $profilePath -Raw -ErrorAction SilentlyContinue
}

if ($profileContent -notlike "*ExtractorOCRv1*") {
    # Agregar el código al perfil
    Add-Content -Path $profilePath -Value "`n$autoActivationCode"
    Write-Host "`n¡Configuración completada!" -ForegroundColor Green
    Write-Host "El entorno virtual se activará automáticamente cuando abras un terminal en:" -ForegroundColor Cyan
    Write-Host $projectPath -ForegroundColor Yellow
    Write-Host "`nReinicia tu terminal o ejecuta: . `$PROFILE" -ForegroundColor Yellow
} else {
    Write-Host "La activación automática ya está configurada en tu perfil de PowerShell." -ForegroundColor Yellow
    Write-Host "Ubicación del perfil: $profilePath" -ForegroundColor Cyan
}

