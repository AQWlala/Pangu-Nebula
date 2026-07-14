$ErrorActionPreference = 'Stop'
$file = 'd:\Pangu Nebula\frontend\src\components\Settings.tsx'
$popupFile = 'd:\Pangu Nebula\_popups.txt'

# Read file content and detect BOM
$bytes = [System.IO.File]::ReadAllBytes($file)
$hasBom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
$content = [System.Text.Encoding]::UTF8.GetString($bytes)
if ($hasBom) { $content = $content.Substring(1) }

# Normalize line endings to LF for splitting
$normalized = $content -replace "`r`n", "`n"
$lines = $normalized -split "`n"

Write-Host "Original line count: $($lines.Count)"

# --- Find Corruption 1: {showJobForm && ( ... )} ---
# Search for the line containing {showJobForm
$jobJsxIdx = -1
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '\{showJobForm') { $jobJsxIdx = $i; break }
}
if ($jobJsxIdx -eq -1) { throw 'Corruption1 start not found' }

# Find closing )} - first standalone )} line after
$jobEndIdx = -1
for ($i = $jobJsxIdx + 1; $i -lt $lines.Count; $i++) {
    if ($lines[$i].Trim() -eq ')}') { $jobEndIdx = $i; break }
}
if ($jobEndIdx -eq -1) { throw 'Corruption1 end not found' }

# Determine deletion start: include JSX comment and leading blank if present
$jobDelStart = $jobJsxIdx
if ($jobJsxIdx -gt 0 -and $lines[$jobJsxIdx - 1] -match '\{/\*') {
    $jobDelStart = $jobJsxIdx - 1
    if ($jobDelStart -gt 0 -and $lines[$jobDelStart - 1].Trim() -eq '') {
        $jobDelStart = $jobDelStart - 1
    }
}
# Determine deletion end: include trailing blank if present
$jobDelEnd = $jobEndIdx
if ($jobEndIdx + 1 -lt $lines.Count -and $lines[$jobEndIdx + 1].Trim() -eq '') {
    $jobDelEnd = $jobEndIdx + 1
}

Write-Host "Corruption1: delete lines $($jobDelStart + 1) to $($jobDelEnd + 1)"

# --- Find Corruption 2: {showMcpServerForm && ( ... )} ---
$mcpJsxIdx = -1
for ($i = $jobEndIdx + 1; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '\{showMcpServerForm') { $mcpJsxIdx = $i; break }
}
if ($mcpJsxIdx -eq -1) { throw 'Corruption2 start not found' }

$mcpEndIdx = -1
for ($i = $mcpJsxIdx + 1; $i -lt $lines.Count; $i++) {
    if ($lines[$i].Trim() -eq ')}') { $mcpEndIdx = $i; break }
}
if ($mcpEndIdx -eq -1) { throw 'Corruption2 end not found' }

$mcpDelStart = $mcpJsxIdx
if ($mcpJsxIdx -gt 0 -and $lines[$mcpJsxIdx - 1] -match '\{/\*') {
    $mcpDelStart = $mcpJsxIdx - 1
    if ($mcpDelStart -gt 0 -and $lines[$mcpDelStart - 1].Trim() -eq '') {
        $mcpDelStart = $mcpDelStart - 1
    }
}
$mcpDelEnd = $mcpEndIdx
if ($mcpEndIdx + 1 -lt $lines.Count -and $lines[$mcpEndIdx + 1].Trim() -eq '') {
    $mcpDelEnd = $mcpEndIdx + 1
}

Write-Host "Corruption2: delete lines $($mcpDelStart + 1) to $($mcpDelEnd + 1)"

# --- Find insertion point: last standalone </div> before ) and } ---
$insertIdx = -1
for ($i = $lines.Count - 1; $i -ge 0; $i--) {
    if ($lines[$i].Trim() -eq '</div>') {
        $nextIdx = $i + 1
        while ($nextIdx -lt $lines.Count -and $lines[$nextIdx].Trim() -eq '') { $nextIdx++ }
        if ($nextIdx -lt $lines.Count -and $lines[$nextIdx].Trim() -eq ')') {
            $insertIdx = $i
            break
        }
    }
}
if ($insertIdx -eq -1) { throw 'Insertion point not found' }

Write-Host "Insertion point: line $($insertIdx + 1)"
Write-Host "  Content: $($lines[$insertIdx])"

# --- Read popup JSX from file ---
$popupBytes = [System.IO.File]::ReadAllBytes($popupFile)
$popupContent = [System.Text.Encoding]::UTF8.GetString($popupBytes)
if ($popupContent.Length -gt 0 -and $popupContent[0] -eq [char]0xFEFF) {
    $popupContent = $popupContent.Substring(1)
}
$popupLines = ($popupContent -replace "`r`n", "`n") -split "`n"
# Remove trailing empty lines
while ($popupLines.Count -gt 0 -and $popupLines[$popupLines.Count - 1].Trim() -eq '') {
    $popupLines = $popupLines[0..($popupLines.Count - 2)]
}
Write-Host "Popup lines to insert: $($popupLines.Count)"

# --- Build new array ---
$newLines = [System.Collections.ArrayList]@()
for ($i = 0; $i -lt $lines.Count; $i++) {
    # Skip corruption 1 block
    if ($i -ge $jobDelStart -and $i -le $jobDelEnd) { continue }
    # Skip corruption 2 block
    if ($i -ge $mcpDelStart -and $i -le $mcpDelEnd) { continue }

    # Insert popups before the insertion point line
    if ($i -eq $insertIdx) {
        foreach ($pl in $popupLines) {
            [void]$newLines.Add($pl)
        }
    }

    [void]$newLines.Add($lines[$i])
}

Write-Host "New line count: $($newLines.Count)"

# --- Write back with CRLF ---
$output = $newLines -join "`r`n"
if (-not $output.EndsWith("`r`n")) {
    $output += "`r`n"
}

$encoding = [System.Text.UTF8Encoding]::new($hasBom)
[System.IO.File]::WriteAllText($file, $output, $encoding)

Write-Host 'SUCCESS: File written with CRLF, BOM preserved'
