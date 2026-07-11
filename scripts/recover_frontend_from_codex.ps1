param(
    [string]$SessionsRoot = "$env:USERPROFILE\.codex\sessions",
    [string]$OutputRoot = "$(Join-Path $PSScriptRoot '..\recovery\frontend-from-codex')"
)

$ErrorActionPreference = 'Stop'
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

$sessionFiles = & rg -l -m 1 'useInstallPrompt|updateServiceWorkerAndDetectIndexChange|resolveAuthNavigation|CarretonMove|useCatalogStore' $SessionsRoot -g '*.jsonl'
$candidates = @()
$matchedCalls = 0
$matchedOutputs = 0

foreach ($sessionFile in $sessionFiles) {
    $calls = @{}

    foreach ($line in Get-Content -LiteralPath $sessionFile) {
        try {
            $record = $line | ConvertFrom-Json -Depth 40
        } catch {
            continue
        }

        if ($record.type -eq 'response_item' -and
            $record.payload.type -eq 'function_call' -and
            $record.payload.name -eq 'shell_command') {
            try {
                $arguments = $record.payload.arguments | ConvertFrom-Json
            } catch {
                continue
            }

            if ($arguments.workdir -notmatch 'FGPY\\web\\registro_viajes') {
                continue
            }

            # Only accept a plain, single-file Get-Content command. Partial reads and
            # combined commands cannot be restored safely as complete source files.
            if ($arguments.command -match '^Get-Content(?:\s+-Path)?\s+(?:''|")?(frontend\\[^\s;''"]+)(?:''|")?(?:\s+-Raw)?\s*$') {
                $relativePath = $Matches[1] -replace '\\', '/'
                $calls[$record.payload.call_id] = [pscustomobject]@{
                    Timestamp = [datetime]$record.timestamp
                    Session = $sessionFile
                    RelativePath = $relativePath
                    Command = $arguments.command
                }
                $matchedCalls++
            }
        }

        if ($record.type -eq 'response_item' -and
            $record.payload.type -eq 'function_call_output' -and
            $calls.ContainsKey($record.payload.call_id)) {
            $call = $calls[$record.payload.call_id]
            $matchedOutputs++
            $rawOutput = [string]$record.payload.output
            $markerMatch = [regex]::Match($rawOutput, 'Output:\r?\n')
            if (-not $markerMatch.Success) {
                continue
            }

            $content = $rawOutput.Substring($markerMatch.Index + $markerMatch.Length)
            if ($content -match 'Warning: truncated output' -or $content -match 'chars truncated') {
                continue
            }

            $candidates += [pscustomobject]@{
                Timestamp = $call.Timestamp
                Session = $call.Session
                RelativePath = $call.RelativePath
                Command = $call.Command
                Content = $content
            }
        }
    }
}

$manifest = @()
foreach ($group in $candidates | Group-Object RelativePath) {
    $selected = $group.Group | Sort-Object Timestamp -Descending | Select-Object -First 1
    $destination = Join-Path $OutputRoot ($selected.RelativePath -replace '/', '\')
    $destinationDirectory = Split-Path -Parent $destination
    New-Item -ItemType Directory -Force -Path $destinationDirectory | Out-Null
    [IO.File]::WriteAllText($destination, $selected.Content, [Text.UTF8Encoding]::new($false))

    $manifest += [pscustomobject]@{
        File = $selected.RelativePath
        Timestamp = $selected.Timestamp.ToUniversalTime().ToString('o')
        Session = [IO.Path]::GetFileName($selected.Session)
        Bytes = ([IO.FileInfo]$destination).Length
        Sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $destination).Hash
    }
}

$manifestPath = Join-Path $OutputRoot 'RECOVERY-MANIFEST.json'
[IO.File]::WriteAllText(
    $manifestPath,
    ($manifest | Sort-Object File | ConvertTo-Json -Depth 5),
    [Text.UTF8Encoding]::new($false)
)

$manifest | Sort-Object File | Format-Table File, Timestamp, Bytes -AutoSize
Write-Output "Matched calls: $matchedCalls; matched outputs: $matchedOutputs; valid candidates: $($candidates.Count)"
Write-Output "Recovered $($manifest.Count) complete files into $OutputRoot"
