import rasterio

# TRANSFORMACJE AFINICZNE ------------------

with rasterio.open("dane/Sentinel-2_L2A_B04.tiff") as src:   # always via "with" — the file gets closed
    print(src.profile)      # everything needed to write a similar file
    print(src.crs)          # coordinate reference system
    print(src.bounds)       # extent in CRS units
    print(src.res)          # pixel size
    print(src.nodata)       # "no data" value

    _row, _col = 10, 10

    x, y = src.xy(_row, _col)          # (row, col) → coordinates of the pixel center
    row, col = src.index(x, y)                      # coordinates → (row, col)

    print(f"[x,y] = [{x},{y}] -> [row,col] = [{row},{col}]")
    print(src.read(1, window=((_row, _row+1), (_col, _col+1))))   # read just this one pixel

    # a click on the map gives WGS 84 (lon, lat) → convert to the raster's CRS first

    lon, lat = 17.895355, 50.595580

    from rasterio.warp import transform
    (x,), (y,) = transform("EPSG:4326", src.crs, [lon], [lat])
    row, col = src.index(x, y)

    print(f"[x,y] = [{x},{y}] -> [row,col] = [{row},{col}]")

# ODCZY PASM ---------------------------

import numpy as np
from rasterio.warp import calculate_default_transform, reproject, Resampling

red_src = rasterio.open("dane/Sentinel-2_L2A_B04.tiff")
nir_src = rasterio.open("dane/Sentinel-2_L2A_B08.tiff")

# checks if both are the same grid
same_grid = (red_src.crs == nir_src.crs
             and red_src.transform == nir_src.transform
             and red_src.shape == nir_src.shape)

print(f"is same grid? = {same_grid}")

# target grid: the red band's grid, in a metric CRS
dst_crs = "EPSG:2180"

dst_transform, width, height = calculate_default_transform(
    red_src.crs, dst_crs, red_src.width, red_src.height, *red_src.bounds,
    resolution=10)                   # Sentinel-2 B04/B08 are natively 10 m

def warp(src):                       # put any band onto the target grid
    out = np.full((height, width), np.nan, dtype="float32") # fills the ndarray used for a reprojection
    reproject(source=rasterio.band(src, 1), destination=out,
              dst_transform=dst_transform, dst_crs=dst_crs,
              dst_nodata=np.nan, resampling=Resampling.bilinear)
    return np.ma.masked_invalid(out)

red, nir = warp(red_src), warp(nir_src)

# OBLICZANIE NDVI ----------------------

# NDVI = (NIR - Red) / (NIR + Red) = (B08 - B04) / (B08 + B04)
with np.errstate(divide="ignore", invalid="ignore"):    # 0 / 0 where both bands are 0
    ndvi = (nir - red) / (nir + red)

ndvi = np.ma.masked_invalid(ndvi)                        # mask NaN / inf


print(f"red.min = {ndvi.min()}, red.max = {ndvi.max()}, red.mean = {ndvi.mean()}")       # statistics ignore nodata
print(f"red.mask.sum = {ndvi.mask.sum()}")                         # how many "no data" pixels

# STATYSTYKI ---------------------------

import geopandas as gpd
import rasterio.mask

with rasterio.open("dane/Sentinel-2_L2A_NDVI.tiff") as src:
    zones = gpd.read_file("lab_geo/dane/opole_districts.geojson").to_crs(src.crs)   # same CRS as the raster!
    pixel_area = abs(src.transform.a * src.transform.e)
    for i, zone in zones.iterrows():
        clipped, _ = rasterio.mask.mask(src, [zone.geometry], crop=True, nodata=np.nan)
        values = clipped[np.isfinite(clipped)]
        zones.loc[i, "coverage"] = values.size * pixel_area / zone.geometry.area   # part of the zone inside the scene
        zones.loc[i, "ndvi_mean"] = values.mean()

# ZAPIS DO PLIKU ----------------------

with rasterio.open("dane/Sentinel-2_L2A_B04.tiff") as src:
    profile = src.profile                     # start from the input's profile…

profile.update(                               # …and describe the grid we computed NDVI on
    crs=dst_crs, transform=dst_transform, width=width, height=height,
    dtype="float32", count=1, nodata=np.nan, compress="deflate",
)

with rasterio.open("wyniki/ndvi.tif", "w", **profile) as dst:
    dst.write(ndvi.filled(np.nan).astype("float32"), 1)
    dst.set_band_description(1, "NDVI")