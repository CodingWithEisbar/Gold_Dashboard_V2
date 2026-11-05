param([string]$PostgresHome = "$PSScriptRoot\..\.tools\postgresql\pgsql")
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath "$PSScriptRoot\..").Path
$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$testRoot = Join-Path $tempRoot ('gold-premium-pg-' + [guid]::NewGuid().ToString('N'))
# PostgreSQL Windows tools cannot reliably spawn each other from a non-ASCII binary path.
Copy-Item -LiteralPath (Resolve-Path -LiteralPath $PostgresHome).Path -Destination "$testRoot\pgsql" -Recurse
$bin = "$testRoot\pgsql\bin"
$data = "$testRoot\data"
$password = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
[IO.File]::WriteAllText("$testRoot\password.txt", $password)
$started = $false
try {
    & "$bin\initdb.exe" -D $data -U postgres --pwfile="$testRoot\password.txt" --auth-host=scram-sha-256 --auth-local=trust --encoding=UTF8 --locale=C
    if ($LASTEXITCODE -ne 0) { throw 'initdb failed' }
    $server = Start-Process -FilePath "$bin\postgres.exe" -ArgumentList @('-D', $data, '-p', '55432', '-h', '127.0.0.1') -WindowStyle Hidden -PassThru -RedirectStandardError "$testRoot\server.log" -RedirectStandardOutput "$testRoot\stdout.log"
    $started = $true
    $env:PGPASSWORD = $password
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        & "$bin\pg_isready.exe" -h 127.0.0.1 -p 55432 -U postgres
        if ($LASTEXITCODE -eq 0) { break }
        if ($server.HasExited) { throw 'PostgreSQL exited; inspect temporary server.log' }
        Start-Sleep -Milliseconds 300
    }
    & "$bin\createdb.exe" -h 127.0.0.1 -p 55432 -U postgres gold_test_integration
    if ($LASTEXITCODE -ne 0) { throw 'createdb failed' }
    $env:TEST_DATABASE_URL = "postgresql+psycopg://postgres:${password}@127.0.0.1:55432/gold_test_integration"
    $env:PATH = "$bin;$env:PATH"
    Push-Location $projectRoot
    try {
        & "$projectRoot\.venv\Scripts\python.exe" -m pytest backend/tests/test_postgres.py -v --basetemp="$testRoot\pytest" -o "cache_dir=$testRoot\cache" --junitxml=artifacts/postgres-tests.xml
        if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL integration tests failed' }
    } finally { Pop-Location }
} finally {
    if ($started) { & "$bin\pg_ctl.exe" -D $data stop -m fast -w }
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:TEST_DATABASE_URL -ErrorAction SilentlyContinue
    # Resolve and verify the exact temporary directory before any recursive deletion.
    $resolved = [IO.Path]::GetFullPath($testRoot)
    if ($resolved.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -and
        [IO.Path]::GetFileName($resolved).StartsWith('gold-premium-pg-')) {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    } else { throw 'Refusing unexpected cleanup target' }
}
