$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath "$PSScriptRoot\..").Path
$destination = Join-Path $root '.tools\security'
New-Item -ItemType Directory -Path $destination -Force | Out-Null
$repositories = @(
    @{ Repo='gitleaks/gitleaks'; Pattern='windows_x64.zip'; Check='checksums.txt' },
    @{ Repo='aquasecurity/trivy'; Pattern='windows-64bit.zip'; Check='checksums.txt' },
    @{ Repo='google/osv-scanner'; Pattern='osv-scanner_windows_amd64.exe'; Check='SHA256SUMS' }
)
$versions = @{}
foreach ($source in $repositories) {
    $release = Invoke-RestMethod -Uri "https://api.github.com/repos/$($source.Repo)/releases/latest"
    $asset = $release.assets | Where-Object { $_.name.EndsWith($source.Pattern) } | Select-Object -First 1
    if (-not $asset) { throw "Missing Windows release asset: $($source.Repo)" }
    $file = Join-Path $destination $asset.name
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $file
    $checksum = $release.assets | Where-Object { $_.name.EndsWith($source.Check) } | Select-Object -First 1
    if (-not $checksum) { throw "Missing official checksum manifest: $($source.Repo)" }
    $manifest = (Invoke-WebRequest -Uri $checksum.browser_download_url).Content
    if ($manifest -is [byte[]]) { $manifest = [Text.Encoding]::UTF8.GetString($manifest) }
    $line = ($manifest -split "`n") | Where-Object { $_.EndsWith($asset.name) } | Select-Object -First 1
    $expected = ($line -split '\s+')[0].ToLowerInvariant()
    if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'Checksum mismatch' }
    if ($asset.name.EndsWith('.zip')) { Expand-Archive -LiteralPath $file -DestinationPath $destination -Force }
    $versions[$source.Repo] = @{version=$release.tag_name; sha256=$expected}
}
$versions | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath "$root\artifacts\security-tool-versions.json"
Write-Output 'Downloaded security tools; official SHA-256 manifests verified.'
