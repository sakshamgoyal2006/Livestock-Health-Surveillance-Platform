$ErrorActionPreference = "Stop"
$ValidationProject = "sih-26128-validation"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$PortableNodeDirectory = Join-Path $RepositoryRoot ".tools\node-v22.23.2-win-x64"
$PortableNpm = Join-Path $PortableNodeDirectory "npm.cmd"
$PortablePython = Join-Path $RepositoryRoot ".tools\python312\python.exe"
$Npm = if (Test-Path -LiteralPath $PortableNpm) {
    # npm lifecycle scripts invoke `node` by name, so expose the bundled
    # runtime to child processes as well as invoking npm by absolute path.
    $env:PATH = "$PortableNodeDirectory;$env:PATH"
    $PortableNpm
} else {
    (Get-Command npm.cmd -ErrorAction Stop).Source
}
$Python = if (Test-Path -LiteralPath $PortablePython) {
    $PortablePython
} else {
    (Get-Command python.exe -ErrorAction Stop).Source
}

# Keep validation isolated from a development stack that may already occupy the
# standard 5432/8000/3000 host ports.
$env:POSTGRES_HOST_PORT = "15432"
$env:API_HOST_PORT = "18000"
$env:WEB_HOST_PORT = "13000"
$env:NEXT_PUBLIC_API_BASE_URL = "http://localhost:18000"
$env:CORS_ORIGINS = "http://localhost:13000"
$env:E2E_BASE_URL = "http://localhost:13000"
$env:E2E_API_BASE_URL = "http://localhost:18000"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )

    & $Command
    $ExitCode = $LASTEXITCODE
    if ($ExitCode -ne 0) {
        throw ("Command failed with exit code {0}: {1}" -f $ExitCode, $Command)
    }
}

$ValidationPassed = $false
try {
    Write-Host "Starting isolated clean Checkpoint 2 database..."
    Invoke-Checked { docker compose --project-name $ValidationProject down --volumes --remove-orphans }
    Invoke-Checked { docker compose --project-name $ValidationProject build }
    Invoke-Checked { docker compose --project-name $ValidationProject up -d db }
    Invoke-Checked { docker compose --project-name $ValidationProject run --rm api alembic upgrade head }
    Invoke-Checked { docker compose --project-name $ValidationProject run --rm api alembic upgrade head }
    Invoke-Checked { docker compose --project-name $ValidationProject run --rm api python -m scripts.seed }
    Invoke-Checked { docker compose --project-name $ValidationProject run --rm api python -m scripts.seed }

    Write-Host "Running backend format, lint, types, unit, and integration suites..."
    Invoke-Checked { docker compose --project-name $ValidationProject run --rm api ruff format --check . }
    Invoke-Checked { docker compose --project-name $ValidationProject run --rm api ruff check . }
    Invoke-Checked { docker compose --project-name $ValidationProject run --rm api mypy app }
    Invoke-Checked { docker compose --project-name $ValidationProject run --rm api pytest -m "not integration" }
    Invoke-Checked { docker compose --project-name $ValidationProject run --rm api pytest -m integration }

    Write-Host "Running reproducible synthetic-only training metadata and evaluation..."
    Invoke-Checked { & $Python -m ruff format --check ml }
    Invoke-Checked { & $Python -m ruff check ml }
    Invoke-Checked { & $Python ml\risk\train_demo.py }
    Invoke-Checked { & $Python ml\risk\evaluate_demo.py }

    Write-Host "Running frontend format, lint, types, and unit suites..."
    Invoke-Checked { & $Npm ci }
    Invoke-Checked { & $Npm --workspace apps/web run format:check }
    Invoke-Checked { & $Npm --workspace apps/web run lint }
    Invoke-Checked { & $Npm --workspace apps/web run typecheck }
    Invoke-Checked { & $Npm --workspace tests/e2e run typecheck }
    Invoke-Checked { & $Npm --workspace apps/web run test }

    Write-Host "Running Checkpoint 1 regression plus Checkpoint 2 triage browser test..."
    Invoke-Checked { docker compose --project-name $ValidationProject up -d api web }
    Invoke-Checked { & $Npm --workspace tests/e2e run install:chromium }
    Invoke-Checked { & $Npm --workspace tests/e2e run test }

    $ValidationPassed = $true
}
finally {
    Write-Host "Stopping isolated validation services..."
    docker compose --project-name $ValidationProject down --volumes --remove-orphans
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Validation cleanup failed; run docker compose --project-name $ValidationProject down --volumes manually."
    }
}

if ($ValidationPassed) {
    Write-Host "Checkpoint 2 validation completed successfully."
}
