# geoemerge

A Python package to interact with and process public geospatial participatory data.

## Installation

You can install this package locally or directly from GitHub using pip:

```bash
pip install git+https://github.com/geo-di-lab/geoemerge.git
```

## Example Usage:
```
from geoemerge import globe_data, download_photos

# Fetch the data
gdf = globe_data(
    protocol="mosquito_habitat_mapper",
    start_date="2024-01-01",
    end_date="2024-01-10",
    country_code="US"
)

# Download the photos and create a labeled CSV
download_photos(
    gdf=gdf,
    photo_url_col="WaterSourcePhotoUrls",
    output_folder="photos",
    num_photos=5,
    export_labels=True
)
```

More usage examples are in the [examples](https://github.com/geo-di-lab/geoemerge/tree/main/examples) folder.