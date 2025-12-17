# Streetview-panorama-scraping

This module helps you scrape panoramas from Google's streetview for given area.

Scraping is done asynchronously using aiohttp and asyncio packages.

The module is built upon and modifies streetview module - https://github.com/robolyst/streetview

# Prereqs

1. In ArcGIS Pro, open **RoadCenterlines** in the map.
2. Run **Generate Points Along Lines**.
   - **Input:** RoadCenterlines  
   - **Point Placement:** By Distance  
   - **Distance Method:** Geodesic
3. Run **Calculate Geometry Attributes**.
   - **Input:** Output from step 2  
   - **New attribute fields:**
     - Longitude — Point x-coordinate
     - Latitude — Point y-coordinate
   - **Coordinate system:** Current Map
4. Export the result as a **CSV**.
5. Drop the saved CSV into the `streetview-panorama-scraping` directory.

# Usage

1. Install required modules: `pip install -r requirements.txt`
2. Change csv_points to the name of the csv you saved from prereqs in `config.yaml`.
3. Run pipeline.py.

```
python pipeline.py
```

# Files

1. `1_get_panoid_info.py` will save data for panoramas and generate a map of panorama locations.

<img width="100%" alt="Drag the layout file to OBS" src="https://i.imgur.com/DzjSq7a.png">

2. `2_download_panoramas.py` will start downloading panoramas to a `panoramas/` directory. Optionally, choose to delete panorama JPGs after projecting, skip entries wthout year, or resume by skipping panoids that already have projected faces (when using --project --delete-pano)

<img width="100%" alt="Drag the layout file to OBS" src="https://i.imgur.com/MDsnjX3.jpg">

3. `3_project_panoramas.py` will project the panoramas into cubical projections with front, back, left and right views as separate images in a `cube_pano/` directory. Optionally, choose to delete panorama JPGs after projection. Uses panoids_with_dates.json to get year/month by panoid.

4. `pipeline.py` will run the above scripts in order.

5. `filter_panoids_by_date.py` is a helper script to filter panoids with available year (required) + month (optional) and throws out data without any date attached to them.

6. `prune_panoramas.py` is a helper script to delete panoramas/*.jpg that are not in panoids_with_dates.json (useful if you already downloaded from the uncleaned list)

# Commands

1. Dry run. Downloads panoid info → filters year → downloads → projects → deletes panos
```
python 1_get_panoid_info.py; $raw=(Get-ChildItem -Filter 'panoids_*.json' | Sort-Object LastWriteTime -Descending | Select-Object -First 1).Name; python filter_panoids_by_date.py --in $raw --out panoids_with_dates.json; python 2_download_panoramas.py --panoids panoids_with_dates.json --require-year --project --delete-pano
```