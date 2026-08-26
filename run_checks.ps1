$ErrorActionPreference = 'Continue'
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot
$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$testData = Join-Path $tempRoot ('joblooper-tests-' + [guid]::NewGuid().ToString('N'))
Copy-Item -LiteralPath (Join-Path $repoRoot 'examples\starter') -Destination $testData -Recurse
$env:JOBLOOPER_DATA_DIR = $testData
$failed = $false

$checks = @(
    @('truth integrity', @('jl.py', 'check')),
    @('adversarial gates', @('tests/test_gates.py')),
    @('output invariants', @('tests/test_pipeline.py')),
    @('semantic matching', @('tests/test_match.py')),
    @('approval and releases', @('tests/test_release.py')),
    @('ground-truth context', @('tests/test_context.py')),
    @('ground-truth review', @('tests/test_truth_review.py')),
    @('pre-generation questions', @('tests/test_preflight.py')),
    @('protected inventory', @('tests/test_inventory_retention.py')),
    @('outcome learning', @('tests/test_learning.py')),
    @('case lifecycle', @('tests/test_case_lifecycle.py')),
    @('PDF extraction', @('tests/test_pdftext.py')),
    @('portability and onboarding', @('tests/test_portability.py')),
    @('single-writer safety', @('tests/test_locking.py')),
    @('standalone skill installation', @('tests/test_installability.py')),
    @('personal/public repository boundary', @('tests/test_repo_policy.py')),
    @('repository policy', @('tools/check_repo.py'))
)

try {
    foreach ($check in $checks) {
        Write-Output "`n== $($check[0]) =="
        & python -B @($check[1])
        if ($LASTEXITCODE -ne 0) { $failed = $true }
    }
}
finally {
    Remove-Item Env:JOBLOOPER_DATA_DIR -ErrorAction SilentlyContinue
    $resolved = [IO.Path]::GetFullPath($testData)
    if ($resolved.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -and $resolved -ne $tempRoot) {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}

if ($failed) {
    Write-Output "`nCHECKS FAILED"
    exit 1
}
Write-Output "`nALL CHECKS PASS"
