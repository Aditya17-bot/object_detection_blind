# Render PDF pages to PNG using the Windows.Data.Pdf WinRT API.
#
# Exists so a generated PDF can actually be LOOKED at on a machine with no
# poppler and no Acrobat -- a hand-built .docx can be schema-valid and still
# lay out wrongly, and page count alone does not show that.
#
#   powershell -ExecutionPolicy Bypass -File tools/pdf_to_png.ps1 `
#       -PdfPath "C:\path\doc.pdf" -OutDir "C:\path\pages" -MaxPages 8

param(
    [Parameter(Mandatory = $true)][string]$PdfPath,
    [Parameter(Mandatory = $true)][string]$OutDir,
    [int]$MaxPages = 10,
    [int]$Width = 1100
)

$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null
[Windows.Data.Pdf.PdfDocument, Windows.Data, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime] | Out-Null

$exts = [System.WindowsRuntimeSystemExtensions].GetMethods()
$asTaskGeneric = ($exts | Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq ('IAsyncOperation' + [char]96 + '1')
    })[0]
$asTaskAction = ($exts | Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction'
    })[0]

function Await($op, $type) {
    $task = $asTaskGeneric.MakeGenericMethod($type).Invoke($null, @($op))
    $task.Wait(-1) | Out-Null
    $task.Result
}
function AwaitAction($action) {
    $task = $asTaskAction.Invoke($null, @($action))
    $task.Wait(-1) | Out-Null
}

if (-not (Test-Path -LiteralPath $OutDir)) {
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
}
$OutDir = (Resolve-Path -LiteralPath $OutDir).Path
$PdfPath = (Resolve-Path -LiteralPath $PdfPath).Path

$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($PdfPath)) ([Windows.Storage.StorageFile])
$pdf = Await ([Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($file)) ([Windows.Data.Pdf.PdfDocument])

$count = [Math]::Min($pdf.PageCount, $MaxPages)
Write-Output "$($pdf.PageCount) pages, rendering $count"

for ($i = 0; $i -lt $count; $i++) {
    $page = $pdf.GetPage($i)
    $stream = New-Object Windows.Storage.Streams.InMemoryRandomAccessStream
    $opts = New-Object Windows.Data.Pdf.PdfPageRenderOptions
    $opts.DestinationWidth = $Width
    AwaitAction ($page.RenderToStreamAsync($stream, $opts))

    $size = [int]$stream.Size
    $reader = New-Object Windows.Storage.Streams.DataReader($stream.GetInputStreamAt(0))
    Await ($reader.LoadAsync($size)) ([uint32]) | Out-Null
    $bytes = New-Object byte[] $size
    $reader.ReadBytes($bytes)
    $reader.Dispose()
    $stream.Dispose()
    if ($page -is [System.IDisposable]) { $page.Dispose() }

    $out = Join-Path $OutDir ("page{0:D2}.png" -f ($i + 1))
    [System.IO.File]::WriteAllBytes($out, $bytes)
    Write-Output "  $out"
}
