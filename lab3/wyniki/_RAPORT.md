# Analiza danych prestrzennych: Laboratiorium 2

> - Autor: Tobiasz Sleziona
> - Nr dziennika: 103868

# GeoPandas

W tym laboratorium użyto danych sensorowych, dzielnic oraz szkół Opola do wyliczenia wyników na temat zanieczyszczenia
powietrza w poszczególnych dzielnicach oraz w pobliżu szkół.

Oto jak to osiągnięto krok po kroku (szczegóły oraz kod zawarte są w `../lab_geo/lab_geopandas.ipynb`):

## Narzędzia
Narzędzia użyte w tym laboratorium:
- **Jupyter** -- menadżer notatników Jupyter
- **GeoPandas** -- biblioteka python do danych przestrzennych wektorowych
- **QGIS**, **Google Maps**

## Dane sensorów

1. Wczytano dane z pliku `pm25_sensors.csv`
2. wyczyszczono dane: usunięto duplikaty, sensory bez współrzędnych lub z niepoprawnymi danymi (<0) oraz poprawiono 
współrzędne, których szerokości i długości zostały zamienione:

```python
# duplikaty
df = df.drop_duplicates()
...
# dane bez współrzędnych
df = df.dropna(subset=["lat", "lon"])
...
# dane z zamienionymi szerokościami i długościami
swapped = df["lat"].between(14, 24.5) & df["lon"].between(49, 55)
df.loc[swapped, ["lat", "lon"]] = df.loc[swapped, ["lon", "lat"]].to_numpy()
...
# dane z niepoprawnymi wartościami sensorów
df = df[df["pm25"] >= 0].reset_index(drop=True)
```

3. Zamieniono tabele DataFrame na GeoDataFrame:

```python
sensors = gpd.GeoDataFrame(
    df,
    geometry=gpd.points_from_xy(df["lon"], df["lat"]),   # x = lon, y = lat!
    crs="EPSG:4326",
)
```

4. Zamieniono ukł. współrz. z EPSG:4326 (dane stopniowe) na EPSG:2180 -- ukł. współrz. specjalny dla danych Polskich: 
`sensors_m = sensors.to_crs("EPSG:2180")`

![img.png](imgs/img.png)

## Dzielnice Opola

1. wczytano dane z pliku `opole_districts.geojson`.
2. Zamieniono ukł współrz. na ten sam co ukł. sensorów: **EPSG:2180** w celu obliczenia powierzchni
> bez zamiany na EPSG:2180 dane nie są w układzie metrowym tylko stopniowym, więc wyliczona powierzchnia nie będzie poprawna.
3. obliczono powierzchnie poszczególnych dzielnic w $km^2$ na podstawie danych w $m^2$.

```python
districts = districts.to_crs("EPSG:2180")           # mandatory!
districts["area_km2"] = districts.area / 1e6        # m² -> km²
```

![img_1.png](imgs/img_1.png)

4. Złączono dane dzielnic z danymi sensorowymi: Każdemu sensorowi przypisana została dzielnica, w której się znajduje.

```python
joined = gpd.sjoin(
    sensors_m,                                   # left: points
    districts[["name", "geometry"]],             # right: polygons (only the columns we need)
    how="left",
    predicate="within",                          # point lies within polygon: sensor lies within district
)
```
5. Obliczono statystyki dzielnic: średnie P25 na podstawie sensorów znajdujących się w dzielnicach oraz liczba sensorów
w dzielnicy:

```python
stats = (joined.groupby("name")                  # name = nazwa dzielnicy
               .agg(pm25_mean=("pm25", "mean"), sensor_count=("pm25", "size"))
               .round(1))

summary = districts.merge(stats, on="name", how="left")
```

![img_2.png](imgs/img_2.png)

(Na diagramie widoczne są dystrykty pokolorowane na podstawie ich średniej wartości P25:
Im ciemniejsze, tym P25 jest większe)

## Szkoły

1. Wczytano dane z pliku: `opole_schools.geojson`.
2. Wyliczono 500-metrowe okrągłe bufory wokół lokalizacji szkół.

```python
buffers["geometry"] = schools.buffer(500)
```

3. Złączono dane dzielnic+sensorów z danymi szkół wraz z ich buforami.

```python
near_schools = gpd.sjoin(sensors_m, buffers[["name", "geometry"]], predicate="within")
```
![img_3.png](imgs/img_3.png)

## Wyniki

1. Wszystkie przetworzone dane dzielnic i sensorów zapisano do dwóch formatów:
- **GeoPackage** zawierające zawierające warstwy obu źródeł danych, oraz
- **GeoJSON** zawierające JSON, użyteczne dla aplikacji webowych. 

```python
# GeoPackage: many layers in one file, any CRS - the default choice
summary.to_file(out / "pm25.gpkg", layer="districts", driver="GPKG")
sensors_m.to_file(out / "pm25.gpkg", layer="sensors", driver="GPKG")

# GeoJSON: for web applications - always save it in EPSG:4326
summary.to_crs("EPSG:4326").to_file(out / "pm25_districts.geojson", driver="GeoJSON")
```

2. W celu sprawdzenia poprawności daych, plik GeoPackage otworzono w aplikacji QGIS:

![img_5.png](imgs/img_5.png)

![img_4.png](imgs/img_4.png)

# Rasterio

(szczegóły oraz kod zawarte są w `geopandas_code.py` oraz `rasterio_code.py`):

## Narzędzia
Narzędzia użyte w tym laboratorium:
- **Rasterio** -- biblioteka python do danych przestrzennych rasterowych

## Preprocessing danych pasmowych

1. Wczytano dane z trzech źródeł: Sentinel 2, Syntetyczne lub własne GeoTIFF-y.
2. Odczytano pasma i statystyki wybranego źródła:

```python
with rasterio.open("S2_L2A_2026-10-06_B04.tiff") as src:
    red = src.read(1, masked=True).astype("float32")

with rasterio.open("S2_L2A_2026-10-06_B08.tiff") as src:
    nir = src.read(1, masked=True).astype("float32")
```

![img.png](imgs/img_9.png)

3. Wyznaczono wspólną siatkę (w ukł. współrz. EPSG:2180) dla obu pasm aby możliwa była algebra rastrowa między
tymi pasmami (piksel na piksel):

```python
dst_crs = "EPSG:2180"
dst_transform, width, height = calculate_default_transform(
    red_src.crs, dst_crs, red_src.width, red_src.height, *red_src.bounds,
    resolution=10)  
```

4. Oba pasma przeprojektowano na tą współną siatkę:

```python
def warp(src):                       # put any band onto the target grid
    out = np.full((height, width), np.nan, dtype="float32")
    
    reproject(source=rasterio.band(src, 1), destination=out,
              dst_transform=dst_transform, dst_crs=dst_crs,
              dst_nodata=np.nan, resampling=Resampling.bilinear)
    return np.ma.masked_invalid(out)

red, nir = warp(red_src), warp(nir_src)
```

## Analiza danych i statystyki

1. Obliczono NDVI za pomocą prostej algebry rastrowej.

> $NDVI = \frac {NIR - RED} {NIR + RED} = \frac {B08 - B04} {B08 + B04} $

```python
with np.errstate(divide="ignore", invalid="ignore"):    # 0 / 0 where both bands are 0
    ndvi = (nir - red) / (nir + red)
ndvi = np.ma.masked_invalid(ndvi)        
```

![img_1.png](imgs/img_6.png)

2. Obliczono statystyki strefowe na podstawie danych dzielnic z pliku `opole_districts.geojson`.

```python
with rasterio.open("ndvi.tif") as src:
    zones = gpd.read_file("opole/opole_districts.geojson").to_crs(src.crs)  # same CRS as the raster!
    pixel_area = abs(src.transform.a * src.transform.e)
    for i, zone in zones.iterrows():
        clipped, _ = rasterio.mask.mask(src, [zone.geometry], crop=True, nodata=np.nan)
        values = clipped[np.isfinite(clipped)]
        zones.loc[i, "coverage"] = values.size * pixel_area / zone.geometry.area  # part of the zone inside the scene
        zones.loc[i, "ndvi_mean"] = values.mean()
```

![img_3.png](imgs/img_8.png)

3. Wygenerowane dane rastrowe NDVI zapisano do pliku.

> Finalne NDVI:
> ![img_10.png](imgs/img_10.png)