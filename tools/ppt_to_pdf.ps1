# Export a .pptx to PDF using PowerPoint automation, so a generated deck can
# actually be looked at (render the PDF with tools/pdf_to_png.ps1).
#
#   powershell -ExecutionPolicy Bypass -File tools/ppt_to_pdf.ps1 `
#       -PptPath "C:\path\deck.pptx" -PdfPath "C:\path\deck.pdf"
#
# PowerPoint is single-instance: New-Object attaches to a copy the user already
# has open. Quitting that would close their window, so this only quits an
# instance it started itself.

param(
    [Parameter(Mandatory = $true)][string]$PptPath,
    [Parameter(Mandatory = $true)][string]$PdfPath
)
$ErrorActionPreference = 'Stop'

$alreadyRunning = [bool](Get-Process POWERPNT -ErrorAction SilentlyContinue)
$ppt = New-Object -ComObject PowerPoint.Application
$pres = $null
try {
    # ReadOnly, no window: leaves any presentation the user has open untouched.
    $pres = $ppt.Presentations.Open($PptPath, $true, $false, $false)
    $pres.SaveAs($PdfPath, 32)   # 32 = ppSaveAsPDF
    Write-Output ("slides: " + $pres.Slides.Count)
}
finally {
    if ($pres) { try { $pres.Close() } catch {} }
    if (-not $alreadyRunning) { try { $ppt.Quit() } catch {} }
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($ppt) | Out-Null
}
Write-Output ("wrote " + $PdfPath)
