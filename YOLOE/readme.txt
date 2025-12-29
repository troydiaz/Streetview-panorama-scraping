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

guardrail 
speed limit sign 
streetlight
utility pole

python .\classify_vis_tp_fp.py --vis "C:\Users\tdiaz\Desktop\Streetview-panorama-scraping\YOLOE\runs\yoloe_speed_limit_sign_vis" --raw-root "C:\Users\tdiaz\Desktop\Streetview-panorama-scraping\cube_pano\2025" --viewer tk


python .\classify_vis_tp_fp.py --vis "C:\Users\tdiaz\Desktop\Streetview-panorama-scraping\YOLOE\runs\yoloe_street_light_vis" --raw-root "C:\Users\tdiaz\Desktop\Streetview-panorama-scraping\cube_pano\2025" --viewer tk
python .\classify_vis_tp_fp.py --vis "C:\Users\tdiaz\Desktop\Streetview-panorama-scraping\YOLOE\runs\yoloe_street_light_vis" --raw-root "C:\Users\tdiaz\Desktop\Streetview-panorama-scraping\cube_pano\2025" --viewer tk

(Get-Content .\yoloe_street_light_vis\false_positive\false_positive_street_light.csv).Count - 1

streetlight 0.6
guardrail 0.8
speed limit sign 0.3
utility pole 0.3 

python .\classify_vis_tp_fp.py --vis "C:\Users\tdiaz\Desktop\Streetview-panorama-scraping\YOLOE\runs\yoloe_street_light_vis" --raw-root "C:\Users\tdiaz\Desktop\Streetview-panorama-scraping\cube_pano\2025" --viewer tk
