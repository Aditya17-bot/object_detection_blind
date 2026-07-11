# BlindAssist — sync the project to Google Drive (G:\My Drive\object_detection_blind)
#
# Usage:  .\sync_to_drive.ps1
#
# Mirrors this folder to the Drive copy, EXCLUDING venv/ and __pycache__/
# (the venv is 26k files, useless in the cloud, and recreatable with
# `python -m venv venv` + `pip install ultralytics opencv-python pyttsx3`).
#
# /MIR makes Drive an exact mirror of this folder (deletes files you deleted
# locally). NOTE: /XD skips venv on BOTH sides, so the stale venv already
# uploaded to Drive stays until you delete it once by hand at drive.google.com.

$src = $PSScriptRoot
$dst = "G:\My Drive\object_detection_blind"

if (-not (Test-Path "G:\My Drive")) {
    Write-Error "G: is not mounted - start Google Drive for Desktop first."
    exit 1
}
if (-not (Test-Path $dst)) {
    Write-Error "$dst not visible yet. Drive is still syncing its file list - try again later, or check the Drive tray icon."
    exit 1
}

robocopy $src $dst /MIR /XD venv __pycache__ .git /XF sync_log.txt /R:2 /W:5 /NP /TEE /LOG:"$src\sync_log.txt"
if ($LASTEXITCODE -le 7) {
    Write-Output "`nSync OK. Drive will now upload the changes in the background."
    exit 0
} else {
    Write-Error "robocopy reported failures (exit code $LASTEXITCODE) - see sync_log.txt"
    exit 1
}
