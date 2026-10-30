$ErrorActionPreference = 'Stop'
docker version
if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop with Linux containers first.' }
foreach ($lang in @('python','java','go')) {
    docker build -t "lb-$lang" (Join-Path $PSScriptRoot $lang)
    if ($LASTEXITCODE -ne 0) { throw "Build failed: $lang" }
}
docker pull grafana/k6:1.3.0
if ($LASTEXITCODE -ne 0) { throw 'k6 image pull failed' }
Write-Host 'Built benchmark images. See README.md for smoke and measured runs.'
