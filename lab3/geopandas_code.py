#
# Has some notes about geopandas and more
#

import geopandas_code as gpd
from shapely.geometry import Point

gdf = gpd.GeoDataFrame(
    {"name": ["A", "B"]},
    geometry=[Point(17.92, 50.67), Point(17.95, 50.66)],
    crs="EPSG:4326",
)
print(gdf.geometry)   # GeoSeries
print(gdf.crs)        # <Geographic 2D CRS: EPSG:4326>

# --------------------------------------

import pandas as pd
import geopandas_code as gpd

df = pd.read_csv("lab_geo/dane/pm25_sensors.csv", parse_dates=["measured_at"])

# CZYSZCZENIE DANYCH --------------------

df = df.drop_duplicates()                       # re-sent messages
df = df.dropna(subset=["lat", "lon"])           # rows without coordinates

# In Poland lat ≈ 49–55, lon ≈ 14–24 → a "lat" of ~17 means swapped columns
swapped = df["lat"].between(14, 24.5) & df["lon"].between(49, 55)
df.loc[swapped, ["lat", "lon"]] = df.loc[swapped, ["lon", "lat"]].to_numpy()

df = df[df["pm25"] >= 0]                        # drop the -999 error code

print(df.head(10))
print(df.describe())

# ZAMIANA NA GEODATAFRAME ---------------

sensors = gpd.GeoDataFrame(
    df,
    geometry=gpd.points_from_xy(df["lon"], df["lat"]),  # x = lon, y = lat!
    crs="EPSG:4326",  # WGS 84 (GPS)
)

sensors.explore(column="pm25", cmap="Oranges")  # interactive map (folium)

# ANALIZA -------------------------------

print(f"{sensors.crs}: WGS84, degrees")  # EPSG:4326 — degrees

sensors_m = sensors.to_crs("EPSG:2180")
print(f"{sensors_m.crs}: PUWG 1992: polish, metres")  # EPSG:2180 — poland, metres

sensors_merc = sensors.to_crs("EPSG:3857")
print(f"{sensors_merc.crs}: web mercator, metres")  # EPSG:3857 — web mercator, metres

###

a, b = sensors.geometry.iloc[0], sensors.geometry.iloc[1]
print(f"{a.distance(b)} degrees")  # in degrees — meaningless!

a, b = sensors_m.geometry.iloc[0], sensors_m.geometry.iloc[1]
print(f"{a.distance(b)} metres: polish projection")  # in metres

a, b = sensors_merc.geometry.iloc[0], sensors_merc.geometry.iloc[1]
print(f"{a.distance(b)} metres: mercator projection")  # in metres


### PRZECHOWUJ W 4326, LICZ W UKŁADZIE METRYCZNYM WŁAŚCIWYM DLA OBSZARU
###
### EPSG:4326 -- WGS 84 - W STOPNIACH
### EPSG:2180 -- PUWG 1992 - DLA CAŁEJ POLSKI, W METRACH
### EPSG:3857 -- WEB MERCATOR, W METRACH (DO KAFLI MAP INTERNETOWYCH, NIE DO POMIARÓW)