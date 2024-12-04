# Streetview-panorama-scraping

This module helps you scrape panoramas from Google's streetview for given area.

Scraping is done asynchronously using aiohttp and asyncio packages.

The module is built upon and modifies streetview module - https://github.com/robolyst/streetview

# Usage

1. Install required modules: `pip install -r requirements.txt`
2. Change center, radius, resolution to your liking in `config.yaml`.
3. Running `1_get_panoid_info.py` will save data for panoramas and generate a map of panorama locations.

<img width="100%" alt="Drag the layout file to OBS" src="https://i.imgur.com/DzjSq7a.png">

3. Running `2_download_panoramas.py` will start downloading panoramas to a `panoramas/` directory

<img width="100%" alt="Drag the layout file to OBS" src="https://i.imgur.com/MDsnjX3.jpg">

4. Running `3_project_panoramas.py` will project the panoramas into cubical projections with front, back, left and right views as separate images in a `cube_pano/` directory.
