# Cached GLOBE data

geoemerge reads these files when the GLOBE API cannot be reached, which is
the case when using Google Colab.

Last rebuilt 2026-09-19 from the GLOBE API, requested range 2010-01-01 to 2026-08-31.

| Protocol | Records | Coverage | Cleaned | Size | Raw | Size |
| --- | ---: | --- | --- | ---: | --- | ---: |
| `land_covers` | 67,936 | 2010-01-01 to 2026-08-31 | `land_covers.parquet` | 6.2 MB | `land_covers_orig.parquet` | 6.3 MB |
| `mosquito_habitat_mapper` | 49,464 | 2017-05-29 to 2026-08-31 | `mosquito_habitat_mapper.parquet` | 2.0 MB | `mosquito_habitat_mapper_orig.parquet` | 2.0 MB |

Both are GeoParquet in EPSG:4326. Each protocol comes in two versions:

- `<protocol>.parquet` carries the column names and cleanups
  `geoemerge.clean_globe_data` applies, and is what `globe_data` falls back to.
- `<protocol>_orig.parquet` is the API's response unchanged: prefixed column
  names, every value a string, `'null'` where a field is empty.
