$ErrorActionPreference = "Stop"
$env:PYTHONUNBUFFERED = "1"

# Run this from your YOLOE folder (where segmentation.py and the .pt weights live)
$python = ".\venv_yoloe\Scripts\python.exe"

# If your updated script is still named segmentation.py, keep this:
$script = ".\segmentation.py"
# If you saved the updated one under a different name (e.g., segmentation_prompt.py), change it:
# $script = ".\segmentation_prompt.py"

$root = "C:\Users\tdiaz\Desktop\Streetview-panorama-scraping\cube_pano\2025"

$conf = 0.30
$iou  = 0.60
$imgsz = 1024
$batch = 16
$printEvery = 250

# Make sure output folder exists
New-Item -ItemType Directory -Force -Path "runs" | Out-Null

# One-by-one object prompts
# "storm drain / catch basin" -> run as two separate objects
$objects = @(
  "fire hydrant",
  "stop sign",
  "speed limit sign",
  "traffic light",
  "traffic cone",
  "barrier",
  "street light",
  "utility pole",
  "sign pole",
  "guardrail",
  "storm drain"
)

foreach ($obj in $objects) {

  # slug for filenames/folders (lowercase, non-alnum -> underscore)
  $slug = $obj.ToLower()
  $slug = [regex]::Replace($slug, "[^a-z0-9]+", "_").Trim("_")

  $outCsv = "runs\yoloe_${slug}_hits.csv"
  $visDir = "runs\yoloe_${slug}_vis"

  Write-Host "`n=== YOLOE run: $obj ==="
  Write-Host "Root: $root"
  Write-Host "CSV : $outCsv"
  Write-Host "VIS : $visDir"

  & $python -u $script `
    --root "$root" `
    --classes "$obj" `
    --out "$outCsv" `
    --conf $conf --iou $iou --imgsz $imgsz --batch $batch `
    --save-vis --vis-dir "$visDir" `
    --print-every $printEvery
}
