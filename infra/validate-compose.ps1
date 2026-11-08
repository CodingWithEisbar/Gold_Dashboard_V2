$ErrorActionPreference = 'Stop'
$validationRoot = Join-Path $PSScriptRoot '..\.tools\compose-validation'
New-Item -ItemType Directory -Path $validationRoot -Force | Out-Null
foreach ($name in @('DB_ADMIN_PASSWORD', 'DB_OWNER_PASSWORD', 'DB_READER_PASSWORD', 'DB_INGESTOR_PASSWORD')) {
    $path = Join-Path $validationRoot $name.ToLowerInvariant()
    Set-Content -LiteralPath $path -Value 'validation-only-placeholder-not-a-secret' -NoNewline
    [Environment]::SetEnvironmentVariable($name + '_FILE', [IO.Path]::GetFullPath($path), 'Process')
}
& "$PSScriptRoot\..\.tools\docker-compose.exe" -f "$PSScriptRoot\..\compose.yaml" config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Compose production config failed' }
$configuration = & "$PSScriptRoot\..\.tools\docker-compose.exe" -f "$PSScriptRoot\..\compose.yaml" config --format json | ConvertFrom-Json
foreach ($property in $configuration.services.PSObject.Properties) {
    $service = $property.Value
    if (-not $service.read_only -or $service.cap_drop -notcontains 'ALL') { throw 'Missing service hardening' }
    foreach ($mount in $service.tmpfs) {
        if (-not $mount.StartsWith('/') -or $mount -notmatch 'uid=\d+,gid=\d+') { throw "Invalid tmpfs options: $mount" }
    }
    if ($property.Name -in @('db','api','worker') -and $service.ports) { throw 'Private service published ports' }
}
if (-not $configuration.networks.database.internal -or -not $configuration.networks.application.internal) { throw 'Internal network missing' }
$btmhVariables = @('BTMH_ENABLED','BTMH_LICENSE_CONFIRMED','BTMH_CONVENTIONS_CONFIRMED','BTMH_MIN_INTERVAL_MINUTES','BTMH_MAX_AGE_HOURS')
foreach ($name in $btmhVariables) {
    if ($null -eq $configuration.services.worker.environment.$name) { throw "Missing worker configuration: $name" }
    if ($null -ne $configuration.services.api.environment.$name) { throw "Crawler configuration leaked into API: $name" }
}
if ($configuration.services.worker.networks.PSObject.Properties.Name -contains 'ingress') { throw 'Worker must not have ingress' }
& "$PSScriptRoot\..\.tools\docker-compose.exe" -f "$PSScriptRoot\..\compose.yaml" -f "$PSScriptRoot\..\compose.local.yaml" config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Compose local config failed' }
$env:S3_BUCKET='validation-bucket'
$env:S3_KMS_KEY_ID='validation-key'
$env:AWS_DEFAULT_REGION='ap-southeast-1'
$env:AWS_ACCESS_KEY_ID='validation-placeholder'
$env:AWS_SECRET_ACCESS_KEY='validation-placeholder'
& "$PSScriptRoot\..\.tools\docker-compose.exe" -f "$PSScriptRoot\..\compose.yaml" -f "$PSScriptRoot\..\compose.backup.yaml" config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Compose backup config failed' }
Write-Output 'Production, local and backup Compose configurations: valid'
$env:POSTGRES_IMAGE='registry.example/gold-postgres@sha256:' + ('a' * 64)
$env:BACKEND_IMAGE='registry.example/gold-backend@sha256:' + ('b' * 64)
$env:FRONTEND_IMAGE='registry.example/gold-frontend@sha256:' + ('c' * 64)
$env:BACKUP_IMAGE='registry.example/gold-backup@sha256:' + ('d' * 64)
$releaseConfig = & "$PSScriptRoot\..\.tools\docker-compose.exe" -f "$PSScriptRoot\..\compose.yaml" -f "$PSScriptRoot\..\compose.release.yaml" -f "$PSScriptRoot\..\compose.backup.yaml" -f "$PSScriptRoot\..\compose.backup-release.yaml" config --format json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Release Compose config failed' }
foreach ($property in $releaseConfig.services.PSObject.Properties) {
    if ($property.Value.build -or $property.Value.image -notmatch '@sha256:[a-f0-9]{64}$') { throw 'Release must use digest-only images without build' }
}
Write-Output 'Release Compose digest-only configuration: valid'
