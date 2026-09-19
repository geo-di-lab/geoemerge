import geopandas as gpd
import pandas as pd
import numpy as np
from typing import Any
import requests
from pathlib import Path

_FALLBACK_DATASETS = {
    "mosquito_habitat_mapper":
        "https://github.com/geo-di-lab/emerge-lessons/raw/refs/heads/main/"
        "docs/data/globe_mosquito.zip",
    "land_covers":
        "https://github.com/geo-di-lab/emerge-lessons/raw/refs/heads/main/"
        "docs/data/globe_land_cover.zip",
}

def _clean_column_names(gdf: gpd.GeoDataFrame, protocol: str) -> gpd.GeoDataFrame:
    """
    Cleans column names for any GLOBE protocol by removing the protocol prefix and 
    capitalizing the remaining name.
    """
    # Remove the prefix from all columns
    prefix = protocol.replace("_", "")
    new_cols = gdf.columns.str.replace(prefix, "", case=False)
    
    # Format column names
    gdf.columns = [
        col[0].upper() + col[1:] if col != 'geometry' and len(col) > 0 else col 
        for col in new_cols
    ]
    
    return gdf

def _clean_larvae_count(val: Any) -> float:
    """
    Helper function to convert GLOBE larvae count strings to floats.
    Handles standard numbers, ranges (e.g., '1-25'), and text with digits.
    """
    if pd.isna(val):
        return val
        
    val_str = str(val).strip()
    
    try:
        return float(val_str)
    except ValueError:
        if '-' in val_str:
            try:
                first, last = val_str.split('-')
                return (float(first.strip()) + float(last.strip())) / 2.0
            except ValueError:
                pass
        
        digits = ''.join([c for c in val_str if c.isdigit()])
        return float(digits) if digits else np.nan

def _identify_genus(row: pd.Series) -> str:
    """
    Helper function to identify the mosquito genus based on the 
    Genus and LastIdentifyStage columns.
    """
    if pd.isna(row.get('Genus')):
        stage = row.get('LastIdentifyStage')
        if pd.isna(stage) or stage == 'identify':
            return 'Unknown'
        else:
            return 'Other'
    return row['Genus']

def _process_land_cover_muc(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Helper function to extract and map Level 1 (more general) MUC codes for the 
    land cover protocol.
    """
    if 'MucCode' not in gdf.columns:
        return gdf

    muc_level1_map = {
        '0': 'Closed Forest',
        '1': 'Woodland',
        '2': 'Shrubland or Thicket',
        '3': 'Dwarf-Shrubland or Dwarf-Thicket',
        '4': 'Herbaceous Vegetation',
        '5': 'Barren',
        '6': 'Wetland',
        '7': 'Open Water',
        '8': 'Cultivated Land',
        '9': 'Urban'
    }

    # Mask to identify rows that actually have a MUC code
    valid_mask = gdf['MucCode'].notna() & (gdf['MucCode'] != 'null')

    # Create column with more general MUC codes (e.g., extract '0' from 'M01')
    level1_str = gdf.loc[valid_mask, 'MucCode'].astype(str).str[1]
    gdf['Level1Code'] = level1_str
    
    # Convert valid strings to numbers (leaves nulls as NaN)
    gdf['label'] = pd.to_numeric(level1_str, errors='coerce')
    
    # Map the descriptions based on the dictionary
    gdf['MucDescription'] = level1_str.map(muc_level1_map)

    return gdf

def clean_globe_data(gdf: gpd.GeoDataFrame, protocol: str) -> gpd.GeoDataFrame:
    """
    Applies the geoemerge cleanups to a GLOBE dataset.

    Use this on a file downloaded directly from the GLOBE API to get the same
    columns globe_data() returns.

    Args:
        gdf (gpd.GeoDataFrame): The raw GLOBE dataset.
        protocol (str): The GLOBE protocol the data belongs to.

    Returns:
        gpd.GeoDataFrame: The processed geodataframe.
    """
    # Column cleanup
    gdf = _clean_column_names(gdf, protocol)
    gdf = gdf.replace('null', np.nan)

    if 'MeasuredAt' in gdf.columns:
        gdf['MeasuredAt'] = pd.to_datetime(gdf['MeasuredAt'], errors='coerce')
        gdf['MeasuredDate'] = gdf['MeasuredAt'].dt.date

        # Sort chronologically
        gdf = gdf.sort_values(by='MeasuredAt')

    # Protocol-specific cleanups
    if protocol == "mosquito_habitat_mapper":
        if 'LarvaeCount' in gdf.columns:
            gdf['LarvaeCount'] = gdf['LarvaeCount'].apply(_clean_larvae_count)

        if 'Genus' in gdf.columns and 'LastIdentifyStage' in gdf.columns:
            gdf['Genus'] = gdf.apply(_identify_genus, axis=1)

    elif protocol == "land_covers":
        gdf = _process_land_cover_muc(gdf)

    elif protocol == "air_temps":
        if 'CurrentTemp' in gdf.columns:
            gdf['CurrentTemp'] = pd.to_numeric(gdf['CurrentTemp'], errors='coerce')

    return gdf

def _manual_download_message(protocol: str, url: str, error: Exception) -> str:
    """
    Explains how to fetch a protocol by hand when the API is unreachable and no
    cached copy of that protocol exists.
    """
    return (
        f"Could not read data from the GLOBE API, and no cached copy of the "
        f"'{protocol}' protocol is available.\n"
        f"Original error: {error}\n\n"
        "To get the data directly:\n"
        "  1. Open this url in a browser:\n"
        f"     {url}\n"
        f"  2. Save the page as '{protocol}.geojson'. In Colab, upload it with the "
        "file browser on the left, or save it to Google Drive and mount the drive.\n"
        "  3. Load it with the same cleanups globe_data applies:\n"
        "       import geopandas as gpd\n"
        "       from geoemerge import clean_globe_data\n"
        f"       gdf = clean_globe_data(gpd.read_file('{protocol}.geojson'), "
        f"'{protocol}')\n"
        "The file already covers the dates requested here, so no further "
        "filtering is needed."
    )

def _load_fallback_dataset(protocol: str, start_date: str, end_date: str,
                           country_code: str = None) -> gpd.GeoDataFrame:
    """
    Loads the cached copy of a protocol and filters it to the requested dates.

    The cached files already carry renamed columns; the cleanups are applied again
    so that the result matches what the API path returns.
    """
    source = _FALLBACK_DATASETS[protocol]
    print(f"Falling back to the cached '{protocol}' dataset:\n  {source}")

    gdf = gpd.read_file(source)
    gdf = clean_globe_data(gdf, protocol)

    # Filter to the requested range, ending at midnight after the last day
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date) + pd.Timedelta(days=1)
    covered = (gdf['MeasuredAt'].min(), gdf['MeasuredAt'].max())
    gdf = gdf[(gdf['MeasuredAt'] >= start) & (gdf['MeasuredAt'] < end)]

    if country_code:
        matches = gdf['CountryCode'].str.upper() == country_code.upper()
        if matches.any():
            gdf = gdf[matches]
        else:
            # The API ignores countrycode on this endpoint, so neither path
            # filters rather than silently returning nothing
            print(
                f"Warning: country code '{country_code}' matched no records, so "
                "no country filter was applied."
            )

    if gdf.empty:
        print(
            f"Warning: the cached dataset has no records between {start_date} and "
            f"{end_date}. It covers {covered[0].date()} to {covered[1].date()}."
        )

    return gdf

def globe_data(protocol: str, start_date: str, end_date: str,
               country_code: str = None, sample: bool = False) -> gpd.GeoDataFrame:
    """
    Fetches and cleans data from the GLOBE API for a specified protocol and date range.

    If the API cannot be reached, protocols with a cached copy are read from that
    copy and filtered to the same date range; the others raise with instructions
    for downloading the data by hand.

    Args:
        protocol (str): The GLOBE protocol to query (e.g., 'mosquito_habitat_mapper', 'land_covers').
        start_date (str): The beginning date in YYYY-MM-DD format.
        end_date (str): The ending date in YYYY-MM-DD format.
        country_code (str, optional): The country code to filter by. Defaults to None.
        sample (bool, optional): If True, returns a smaller sample dataset. Defaults to False.

    Returns:
        gpd.GeoDataFrame: The processed geodataframe.
    """

    # Get URL to data from GLOBE API
    base_url = "https://api.globe.gov/search/v1/measurement/"

    params = [
        f"protocols={protocol}",
        "datefield=measuredDate",
        f"startdate={start_date}",
        f"enddate={end_date}",
        "geojson=TRUE",
        f"sample={str(sample).upper()}"
    ]

    if country_code:
        params.append(f"countrycode={country_code}")

    url = f"{base_url}?{'&'.join(params)}"

    # Fetch data into a GeoDataFrame
    try:
        gdf = gpd.read_file(url)
    except Exception as e:
        if protocol not in _FALLBACK_DATASETS:
            raise RuntimeError(_manual_download_message(protocol, url, e))

        print(f"Could not read data from the GLOBE API: {e}")
        return _load_fallback_dataset(protocol, start_date, end_date, country_code)

    if gdf.empty:
        print("Warning: The API returned an empty dataset for the given parameters.")
        return gdf

    return clean_globe_data(gdf, protocol)

def download_photos(gdf: gpd.GeoDataFrame, photo_url_col: str,
                    output_folder: str, num_photos: int = 10,
                    export_labels: bool = False) -> None:
    """
    Downloads photos from a GLOBE API GeoDataFrame based on a specified URL column.
    Handles multiple semicolon-separated URLs per row, renames files based on the 'Id' 
    column to prevent overwrites, and outputs relative paths in the metadata CSV.

    Args:
        gdf (gpd.GeoDataFrame): The processed GLOBE dataset.
        photo_url_col (str): The name of the column containing the photo URLs.
        output_folder (str): The local directory path to save the downloaded images.
        num_photos (int, optional): The maximum number of photos to download. Defaults to 10.
        export_labels (bool, optional): If True, creates a CSV mapping relative paths
                                        to the original row metadata. Defaults to False.
    """
    if photo_url_col not in gdf.columns:
        raise ValueError(f"Column '{photo_url_col}' not found in the GeoDataFrame.")

    # Create the output directory if it doesn't exist
    out_dir = Path(output_folder)
    out_dir.mkdir(parents=True, exist_ok=True)

    downloaded_count = 0
    metadata_records = []
    
    # Standard dictionary to keep track of how many photos belong to a specific ID
    id_counts = {}

    # Drop rows where the photo URL column is null
    valid_rows = gdf.dropna(subset=[photo_url_col])

    print(f"Starting photo download... Target: {num_photos} photos.")

    for index, row in valid_rows.iterrows():
        if downloaded_count >= num_photos:
            break

        # Extract the row's unique identifier, defaulting to the index if 'Id' is missing
        row_id = str(row.get('Id', index))

        # Extract URLs, handling multiple URLs separated by semicolons
        raw_url_string = str(row[photo_url_col])
        urls = [url.strip() for url in raw_url_string.split(";") if url.strip()]

        for url in urls:
            if downloaded_count >= num_photos:
                break
            
            # Create unique filename for photo based on the row's ID and the count of photos from that ID
            id_counts[row_id] = id_counts.get(row_id, 0) + 1
            filename = f"{row_id}_{id_counts[row_id]}.jpg"
            
            # Relative path to photo
            local_save_path = out_dir / filename
            relative_csv_path = str(Path(output_folder) / filename)

            try:
                # Download photo (streaming to handle large files)
                response = requests.get(url, stream=True, timeout=10)
                response.raise_for_status()

                # Save the image
                with open(local_save_path, 'wb') as file:
                    for chunk in response.iter_content(chunk_size=8192):
                        file.write(chunk)
                
                downloaded_count += 1
                
                # If labels are needed, assign the row's data to this photo
                if export_labels:
                    ordered_dict = {
                        'DownloadedPhotoPath': relative_csv_path,
                        'OriginalPhotoUrl': url
                    }
                    ordered_dict.update(row.to_dict())
                    metadata_records.append(ordered_dict)
                    
            except requests.exceptions.RequestException as e:
                print(f"Failed to download {url}: {e}")
                continue

    print(f"Successfully downloaded {downloaded_count} photos to '{out_dir}'.")

    # Export CSV if requested
    if export_labels and metadata_records:
        csv_path = out_dir / "photo_metadata_labels.csv"
        
        # Convert to DataFrame
        metadata_df = pd.DataFrame(metadata_records)
        if 'geometry' in metadata_df.columns:
            metadata_df['geometry'] = metadata_df['geometry'].astype(str)
            
        metadata_df.to_csv(csv_path, index=False)
        print(f"Metadata labels exported to: {csv_path}")
