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
3. Run pipeline.py

# Files

1. `1_get_panoid_info.py` will save data for panoramas and generate a map of panorama locations.

<img width="100%" alt="Drag the layout file to OBS" src="https://i.imgur.com/DzjSq7a.png">

2. `2_download_panoramas.py` will start downloading panoramas to a `panoramas/` directory

<img width="100%" alt="Drag the layout file to OBS" src="https://i.imgur.com/MDsnjX3.jpg">

3. `3_project_panoramas.py` will project the panoramas into cubical projections with front, back, left and right views as separate images in a `cube_pano/` directory.
