python Inference.py --model_path ./weights/FastSAM.pt --img_path ./images/dogs.jpg --text_prompt "the yellow dog"


.\.venv\Scripts\Activate.ps1
C:\Users\tdiaz\venvs\ultra310\Scripts\python.exe .\test_segmentation.py

Months: [4, 5, 7, 8]
Counts: {4: 7512, 5: 26770, 7: 770, 8: 176}
Min/Max: (4, 8)

$env:PYTHONUNBUFFERED="1"
.\venv_yoloe\Scripts\python.exe -u segmentation.py `
  --root "C:\Users\tdiaz\Desktop\Streetview-panorama-scraping\cube_pano\2025" `
  --out "runs\yoloe_manhole_hits.csv" `
  --conf 0.30 --iou 0.60 --imgsz 1024 --batch 16 `
  --save-vis --vis-dir "runs\yoloe_manhole_vis" `
  --print-every 250
