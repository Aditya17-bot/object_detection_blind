# Transcode any Windows-decodable audio (AAC/.mp4, .m4a, .3gp, .mp3, .wma) to WAV.
#
# Why this exists: the ASR condition needs PCM, WhatsApp voice notes are AAC,
# and this machine has no ffmpeg. Windows Media Foundation already ships an AAC
# decoder, so nothing has to be downloaded. asr_collect.py handles the resample
# and downmix itself, so the output rate/channel count here does not matter.
#
#   powershell -ExecutionPolicy Bypass -File tools/aac_to_wav.ps1 `
#       -InputPath "C:\path\in.mp4" -OutputPath "C:\path\out.wav"

param(
    [Parameter(Mandatory = $true)][string]$InputPath,
    [Parameter(Mandatory = $true)][string]$OutputPath
)

$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null
[Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.StorageFolder, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
[Windows.Media.MediaProperties.MediaEncodingProfile, Windows.Media, ContentType = WindowsRuntime] | Out-Null
[Windows.Media.Transcoding.MediaTranscoder, Windows.Media, ContentType = WindowsRuntime] | Out-Null

$exts = [System.WindowsRuntimeSystemExtensions].GetMethods()

$asTaskGeneric = ($exts | Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq ('IAsyncOperation' + [char]96 + '1')
    })[0]

# TranscodeAsync() returns IAsyncActionWithProgress<double>, NOT IAsyncAction --
# picking the plain IAsyncAction overload fails at Invoke with a __ComObject
# cast error that says nothing about the real cause.
$asTaskProgress = ($exts | Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq ('IAsyncActionWithProgress' + [char]96 + '1')
    })[0]

function Await($op, $type) {
    $task = $asTaskGeneric.MakeGenericMethod($type).Invoke($null, @($op))
    $task.Wait(-1) | Out-Null
    $task.Result
}

function AwaitProgress($action, $progressType) {
    $task = $asTaskProgress.MakeGenericMethod($progressType).Invoke($null, @($action))
    $task.Wait(-1) | Out-Null
}

$InputPath = (Resolve-Path -LiteralPath $InputPath).Path
$outDir = Split-Path -Parent $OutputPath
if (-not (Test-Path -LiteralPath $outDir)) {
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
}
$outDir = (Resolve-Path -LiteralPath $outDir).Path
$outName = Split-Path -Leaf $OutputPath

$src = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($InputPath)) ([Windows.Storage.StorageFile])
$folder = Await ([Windows.Storage.StorageFolder]::GetFolderFromPathAsync($outDir)) ([Windows.Storage.StorageFolder])
$dst = Await ($folder.CreateFileAsync($outName,
        [Windows.Storage.CreationCollisionOption]::ReplaceExisting)) ([Windows.Storage.StorageFile])

$profile = [Windows.Media.MediaProperties.MediaEncodingProfile]::CreateWav(
    [Windows.Media.MediaProperties.AudioEncodingQuality]::High)

$transcoder = New-Object Windows.Media.Transcoding.MediaTranscoder
$prep = Await ($transcoder.PrepareFileTranscodeAsync($src, $dst, $profile)) ([Windows.Media.Transcoding.PrepareTranscodeResult])

if (-not $prep.CanTranscode) {
    throw "cannot transcode: $($prep.FailureReason)"
}
AwaitProgress ($prep.TranscodeAsync()) ([double])

$size = (Get-Item -LiteralPath $OutputPath).Length
Write-Output "wrote $OutputPath ($([math]::Round($size / 1MB, 1)) MB)"
