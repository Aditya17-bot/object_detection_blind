# Convert a .docx to PDF with the installed Word, headless.
#
# Used to VERIFY paper/build_docx.py output: a hand-built OOXML package can be
# schema-valid and still lay out wrongly, and only a render shows that. Pair it
# with tools/pdf_to_png.ps1 to look at the pages.
#
#   powershell -ExecutionPolicy Bypass -File tools/docx_to_pdf.ps1 `
#       -DocxPath "C:\path\doc.docx" -PdfPath "C:\path\doc.pdf"

param(
    [Parameter(Mandatory = $true)][string]$DocxPath,
    [Parameter(Mandatory = $true)][string]$PdfPath
)

$ErrorActionPreference = 'Stop'
$DocxPath = (Resolve-Path -LiteralPath $DocxPath).Path

# A Word instance left running from a previous failed conversion holds a lock
# on the file and the next Open() blocks forever with no error.
Get-Process WINWORD -ErrorAction SilentlyContinue | Stop-Process -Force

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    # (path, ConfirmConversions, ReadOnly, AddToRecentFiles)
    $doc = $word.Documents.Open($DocxPath, $false, $true, $false)
    $doc.Repaginate()
    Write-Output ("pages: " + $doc.ComputeStatistics(2))
    Write-Output ("words: " + $doc.ComputeStatistics(0))
    # wdExportFormatPDF = 17
    $doc.ExportAsFixedFormat($PdfPath, 17, $false, 0, 0, 0, 0, 0, $true, $true,
        0, $true, $true, $false)
    Write-Output "wrote $PdfPath"
    $doc.Close(0)
}
finally {
    # $word.Quit() needs a [ref] under PowerShell 5.1; killing is simpler and
    # leaves nothing holding the file.
    Get-Process WINWORD -ErrorAction SilentlyContinue | Stop-Process -Force
}
