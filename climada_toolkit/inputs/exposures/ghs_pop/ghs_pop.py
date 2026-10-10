"""Download and subset GHS-POP R2023A population counts on the native WGS84 grid."""

import logging
from pathlib import Path
import re
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_window
from shapely import contains_xy
from shapely.geometry import box

from climada.entity import Exposures
from climada.util.config import CONFIG
from climada.util import coordinates as u_coord
from climada.util import files_handler as u_fh

LOGGER = logging.getLogger(__name__)


# Default file storage settings
# We use subfolders within the local storage set in climada's config file
# See https://climada-python.readthedocs.io/en/latest/development/Guide_Configuration.html#configuration
LOCAL_DATA_DIR = CONFIG.local_data.system.dir()
DOWNLOAD_DIR = LOCAL_DATA_DIR / "exposures" / "ghs_pop" / "raw"
OUTPUT_DIR = LOCAL_DATA_DIR / "exposures" / "ghs_pop" / "hdf5"

# Currently supported GHS options
# (Other map projections and future population projections can be added later)
GHS_POP_RELEASE = "R2023A"
GHS_POP_PROJECTION = "EPSG:4326"  # WGS84
GHS_POP_YEARS = list(range(1975, 2031, 5))
GHS_POP_RESOLUTIONS = [3, 30]  # Arcseconds
GHS_POP_NODATA = -200
GHS_POP_TILE_COUNT = 348  # Verified for all supported epoch/resolution listings.

# Data download URL
GHS_POP_BASE_URL = (
    "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_POP_GLOBE_R2023A/"
)
# Metadata URL
GHS_POP_INDEX_BASE_URL = "https://human-settlement.emergency.copernicus.eu/download/"
GHS_POP_INDEX_FILENAME = "GHSL_data_4326_shapefile.zip"
GHS_POP_INDEX_URL = GHS_POP_INDEX_BASE_URL + GHS_POP_INDEX_FILENAME

GLOBAL_BOUNDS = (-180, -90, 180, 90)



def load_ghs_pop(
    country: str | None = None,
    bounding_box: tuple[float, float, float, float] | None = None,
    year: int = 2020,
    resolution: int = 3,
    drop_zeros: bool = True,
    download_dir: Path | str = DOWNLOAD_DIR,
    output_dir: Path | str = OUTPUT_DIR,
    output_filename: str | None = None,
    force_redownload: bool = False,
):
    """Create a population exposure dataset from GHS-POP data.

    At minimum this needs a country ISO3 code or a bounding box. The function 
    has defaults for everything else.
    
    The function downloads any required input files, subsets, constructs 
    a CLIMADA ``Exposures`` object and optionally saves it.

    Select one epoch (default to the most recent: 2020) and WGS84 resolution 
    (default to the highest: 3 arcseconds), with a country ISO3 code, bounding 
    box or both. We recommend ``resolution=30`` for hazard data at 30 arcseconds 
    resolution or  coarser: there is no point having Exposures at a finer 
    resolution than your hazard.
    
    Bounding boxes cannot wrap across the antimeridian; split such requests 
    into separate boxes and concatenate with ``Exposures.concat``.

    Subsetting to country and box geometries selects grid points with centres 
    within the geometry. This may cause inaccuracies near complex borders and 
    coastlines, particularly at 30 arcseconds.

    ``drop_zeros=True`` removes grid cells with no population and saves disk 
    space in sparsely populated regions. Default is True.

    All downloaded data is saved, and will be re-downloaded if 
    ``force_redownload=True``. The exception is the GHS population index file. 
    If you want to redownload this call ``clear_ghs_pop_index`` first.
    
    Returns one ``Exposures`` object. Also writes to HDF5  when 
    ``output_filename`` is given, using ``output_dir / output_filename``.
    """

    # Setup and validate inputs
    # ------------------------------

    # Create output directory if it is within CLIMADA CONFIG local storage
    if output_filename is not None and not Path(output_dir).is_dir():
        if LOCAL_DATA_DIR.is_dir() and LOCAL_DATA_DIR in Path(output_dir).parents:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
        else:
            raise FileNotFoundError(f"Output directory does not exist: {output_dir}")

    year, resolution = standardise_ghs_pop_parameters(year, resolution)
    country, bounding_box = standardise_ghs_geom_parameters(country, bounding_box)

    # Select and download the required raster tiles and index
    # ------------------------------
    download_ghs_pop_tiles(
        country=country,
        bounding_box=bounding_box,
        year=year,
        resolution=resolution,
        download_dir=download_dir,
        force_redownload=force_redownload,
    )

    # Create an Exposure object
    # ------------------------------
    exposure = create_ghs_pop_exposure(
        country=country,
        bounding_box=bounding_box,
        year=year,
        resolution=resolution,
        drop_zeros=drop_zeros,
        download_dir=download_dir
    )

    # Write to HDF5 if requested
    # ------------------------------
    if output_filename is not None:
        output_path = Path(output_dir) / output_filename
        exposure.write_hdf5(output_path)
        LOGGER.info("Wrote GHS-POP exposure to %s (%.2f MiB)", output_path, output_path.stat().st_size / 1024**2)
    return exposure


def standardise_ghs_pop_parameters(
    year: int = 2020,
    resolution: int = 3
):
    """Validate and normalize a GHS-POP file request's parameters.

    Return ``(year, resolution)``. Supply a country ISO3
    code, a WGS84 box ``(min_lon, min_lat, max_lon, max_lat)``, or both.

    See constants at the start of the module for valid years and resolutions.
    """
    if isinstance(year, (bool, np.bool_)) or not isinstance(year, (int, np.integer)):
        raise ValueError("year must be an integer")
    if year not in GHS_POP_YEARS:
        raise ValueError(f"year must be one of {GHS_POP_YEARS}")
    if isinstance(resolution, (bool, np.bool_)) or not isinstance(
        resolution, (int, np.integer)
    ):
        raise ValueError("resolution must be an integer number of arcseconds")
    if resolution not in GHS_POP_RESOLUTIONS:
        raise ValueError(f"resolution must be one of {GHS_POP_RESOLUTIONS} arcseconds")
    
    return int(year), int(resolution)
    

def standardise_ghs_geom_parameters(
    country: str | None = None,
    bounding_box: tuple[float, float, float, float] | None = None,
) -> tuple[str | None, tuple[float, float, float, float] | None]:
    """Validate and normalize GHS-POP geometry parameters.

    Return ``(country, bounding_box)``. Supply a country ISO3 code, a WGS84 box
    ``(min_lon, min_lat, max_lon, max_lat)``, or both.
    """

    if country is None and bounding_box is None:
        raise ValueError("Provide a country ISO3 code or bounding_box")
    if country is not None:
        if not isinstance(country, str) or not re.fullmatch(r"[A-Za-z]{3}", country):
            raise ValueError("country must be one ISO3 country code")
        country = country.upper()
    if bounding_box is not None:
        try:
            bounds = np.asarray(bounding_box, dtype=float)
        except (TypeError, ValueError) as exc:
            raise ValueError("bounding_box must contain four numeric values") from exc
        if bounds.shape != (4,) or not np.isfinite(bounds).all():
            raise ValueError("bounding_box must contain four finite numeric values")
        min_lon, min_lat, max_lon, max_lat = bounds
        if not (-180 <= min_lon < max_lon <= 180 and -90 <= min_lat < max_lat <= 90):
            raise ValueError(
                "bounding_box must have increasing longitudes within [-180, 180] "
                "and increasing latitudes within [-90, 90]"
            )
        bounding_box = tuple(float(value) for value in bounds)

    return country, bounding_box


def download_ghs_pop_index(
    download_dir: Path | str = DOWNLOAD_DIR
):
    """Download/cache the official WGS84 index and return its ZIP ``Path``.

    The directory must exist. Download directly into it and validate the ZIP;
    an existing readable index is reused unless ``force_redownload=True``.
    Retry failed downloads with ``force_redownload=True``.
    """
    download_dir = Path(download_dir)
    
    if not download_dir.is_dir():
        raise FileNotFoundError(f"Download directory does not exist: {download_dir}")
    index_path = download_dir / GHS_POP_INDEX_FILENAME
    if index_path.is_file():
        LOGGER.info("Reusing GHS-POP tile index: %s", index_path)
        return index_path

    LOGGER.info("Downloading GHS-POP tile index: url=%s local_path=%s", GHS_POP_INDEX_URL, index_path)
    u_fh.download_file(GHS_POP_INDEX_URL, download_dir=download_dir)
    return index_path


def build_ghs_pop_filename(tile: str, year: int = 2020, resolution: int = 3):
    """Return the TIFF filename for a tile, for example ``R8_C17``
    """
    year, resolution = standardise_ghs_pop_parameters(year, resolution)
    if not isinstance(tile, str) or not re.fullmatch(r"R[1-9][0-9]*_C[1-9][0-9]*", tile):
        raise ValueError("tile must be an ID such as R8_C17")
    filename_base = (
        f"GHS_POP_E{year}_GLOBE_{GHS_POP_RELEASE}_4326_"
        f"{resolution}ss_V1_0_{tile}"
    )
    filename = f"{filename_base}.tif"
    product = f"GHS_POP_E{year}_GLOBE_{GHS_POP_RELEASE}_4326_{resolution}ss"
    url = f"{GHS_POP_BASE_URL}{product}/V1-0/tiles/{filename_base}.zip"
    return filename, url


def download_ghs_pop_tiles(
    country: str | None = None,
    bounding_box: tuple[float, float, float, float] | None = None,
    year: int = 2020,
    resolution: int = 3,
    download_dir: Path | str = DOWNLOAD_DIR,
    force_redownload: bool = False,
):
    """Select, download and extract the required raw GHS TIFF tiles and return 
    paths.
    
    The method first downloads the GHS-POP index geodata which contains 
    information on the files we'll need to request for download.

    ``force_redownload=True`` refreshes TIFFs. The index is will only be 
    downloaded once until ``clear_ghs_pop_index`` is called or the file is 
    removed. Download directories outside of CLIMADA's config directories must 
    already exist.

    See :func:`load_ghs_pop` for details of available years, resolutions, 
    and GHS-POP release.
    """

    # Setup and standardise
    # --------------------------------
    year, resolution = standardise_ghs_pop_parameters(year, resolution)
    country, bounding_box = standardise_ghs_geom_parameters(country, bounding_box)
    geometry = _combine_geometry(country, bounding_box)

    download_dir = Path(download_dir)
    if not download_dir.is_dir():
        if LOCAL_DATA_DIR.is_dir() and LOCAL_DATA_DIR in download_dir.parents:
            download_dir.mkdir(parents=True, exist_ok=True)
        else:
            raise FileNotFoundError(f"Download directory does not exist: {download_dir}")

    # Download and GHS-POP TIFF file metadata
    # --------------------------------
    index_path = download_ghs_pop_index(download_dir)

    # Select GHS-POP files to download
    # --------------------------------
    tiles = gpd.read_file(f"zip://{index_path.resolve()}")
    overlaps = tiles.geometry.intersection(geometry)
    selected = tiles.loc[[part.area > 0 for part in overlaps]]
    if selected.empty:
        raise ValueError("No published GHS-POP tiles overlap the selected geometry")
    LOGGER.info("Downloading or reusing %s GHS-POP tile(s) from %s", len(selected), download_dir)

    file_paths = []
    for tile in selected.tile_id:
        filename, url = build_ghs_pop_filename(tile, year, resolution)
        raster_path = download_dir / filename
        archive_path = raster_path.with_suffix(".zip")

        if raster_path.is_file() and not force_redownload:
            LOGGER.info("Reusing TIFF: %s", raster_path.name)
            file_paths.append(raster_path)
            continue

        LOGGER.info("Downloading and extracting TIFF: %s", archive_path.name)
        u_fh.download_file(url, download_dir=download_dir)

        with zipfile.ZipFile(archive_path) as archive:
            archive.extract(filename, path=download_dir)
        archive_path.unlink()

        file_paths.append(raster_path)

    return file_paths


def _combine_geometry(country, bounding_box):
    if country is not None:
        geometry = u_coord.get_land_geometry([country])
        if bounding_box is not None:
            geometry = geometry.intersection(box(*bounding_box))
    else:
        geometry = box(*bounding_box)
    if geometry.is_empty or geometry.area == 0:
        raise ValueError("The selected country/bounding-box intersection is empty")
    return geometry



def create_ghs_pop_exposure(
    country: str | None = None,
    bounding_box: tuple[float, float, float, float] | None = None,
    year: int = 2020,
    resolution: int = 3,
    drop_zeros: bool = True,
    download_dir: Path | str = DOWNLOAD_DIR,
):
    """Construct a GHS population ``Exposures`` object from already-saved TIFFs.

    No downloads occur. Required TIFF filenames are derived from the selected
    tiles, year and resolution. See :func:`load_ghs_pop` for details of 
    parameters.
    """
    year, resolution = standardise_ghs_pop_parameters(year, resolution)
    country, bounding_box = standardise_ghs_geom_parameters(country, bounding_box)

    # Identify the .tif files we need
    # -------------------------------
    geometry = _combine_geometry(country, bounding_box)
    download_dir = Path(download_dir)
    index_path = download_dir / GHS_POP_INDEX_FILENAME
    tiles = gpd.read_file(f"zip://{index_path.resolve()}")
    overlaps = tiles.geometry.intersection(geometry)
    selected = tiles.loc[[part.area > 0 for part in overlaps]]
    if selected.empty:
        raise ValueError("No published GHS-POP tiles overlap the selected geometry")
        
    file_paths = [
        download_dir / build_ghs_pop_filename(tile, year, resolution)[0]
        for tile in selected.tile_id
    ]
    missing = [str(path) for path in file_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Required GHS-POP TIFFs are missing: {missing}")

    # Read TIF files into memory and subset
    # -----------------------------------------------------------------------
    frames = []
    for file_path, tile in zip(file_paths, selected.itertuples()):
        with rasterio.open(file_path) as src:
            if src.crs != rasterio.crs.CRS.from_epsg(4326) or src.count != 1:
                raise ValueError(f"Expected a single-band WGS84 raster: {file_path}")
            if not np.allclose(src.bounds, tile.geometry.bounds, rtol=0, atol=1e-7):
                raise ValueError(f"Raster footprint differs from indexed tile {tile.tile_id}: {file_path}")
            
            overlap = geometry.intersection(box(*src.bounds))
            if overlap.is_empty or overlap.area == 0:
                raise ValueError(f"No overlap between selected geometry and raster footprint: {file_path}")


            window = geometry_window(src, [overlap])
            LOGGER.info("Reading GHS-POP window: local_path=%s window=%s", file_path, window)
            data = src.read(1, window=window, masked=True)
            transform = src.window_transform(window)

            # Compute the longitude and latitude of each cell centre within the window.
            longitudes = transform.c + (np.arange(data.shape[1]) + 0.5) * transform.a
            latitudes = transform.f + (np.arange(data.shape[0]) + 0.5) * transform.e

            # Determine which cells are inside the desired geometry.
            inside = contains_xy(geometry, longitudes[None, :], latitudes[:, None])
            valid = inside & ~np.ma.getmaskarray(data) & (data.data != -200)

            if np.any(valid & (~np.isfinite(data.data) | (data.data < 0))):
                raise ValueError(f"Negative or non-finite population values in selected cells: {file_path}")
            if drop_zeros:
                valid &= data.data != 0
            rows, columns = np.nonzero(valid)
            frames.append(pd.DataFrame({
                "longitude": longitudes[columns],
                "latitude": latitudes[rows],
                "value": data.data[rows, columns],
            }))

    points = pd.concat(frames, ignore_index=True)
    if points[["latitude", "longitude"]].round(8).duplicated().any():
        raise ValueError(f"Duplicate source cells found in GHS-POP tiles: {file_paths}")

    # Metadata describes counts, not population density or adjusted totals.
    # -------------------------------------------------------------------
    epoch_kind = "projection" if year >= 2025 else "estimate"
    exposure = Exposures(
        points, crs="EPSG:4326", ref_year=year, value_unit="people",
        description=(
            f"GHS-POP {GHS_POP_RELEASE}, {year} {epoch_kind}, WGS84, {resolution} arcseconds; "
            f"tiles={selected.tile_id.tolist()}; country={country} & bounds={bounding_box}; "
            f"grid cells centroids intersected with geometry; source={GHS_POP_BASE_URL}"
        ),
    )
    if points.empty:
        LOGGER.info("Selected GHS-POP cells contain only zeros; returning an empty exposure")
    LOGGER.info(
        "Created GHS-POP exposure: year=%s resolution=%s tiles=%s points=%s population=%s",
        year, resolution, selected.tile_id.tolist(), len(points), exposure.value.sum(),
    )
    return exposure



# Functions to clear cached GHS-POP files (downloads and outputs)
# ---------------------------------------------------------------

def clear_ghs_pop_downloads(download_dir: Path | str = DOWNLOAD_DIR):
    """Delete cached GHS-POP ZIPs/TIFFs; return deleted paths.

    Remove downloaded ``GHS_POP_*.zip`` and ``GHS_POP_*.tif`` files within  
    ``download_dir``.

    These are not Exposures data so can be deleted after use and redownloaded 
    if needed.
    """
    download_dir = Path(download_dir)
    if not download_dir.is_dir():
        raise FileNotFoundError(f"Download directory does not exist: {download_dir}")

    deleted = []
    for path in sorted(download_dir.iterdir()):
        if path.is_file() and path.name.startswith("GHS_POP_") and path.suffix in (".zip", ".tif"):
            path.unlink()
            deleted.append(path)
            LOGGER.info("Deleted GHS-POP download: %s", path)
    return deleted


def clear_ghs_pop_outputs(output_dir: Path | str = OUTPUT_DIR):
    """Delete created GHS-POP ``*.hdf5`` files and return their paths.

    Remove every HDF5 file directly within the existing output directory. This 
    does not remove raw TIFF downloads.
    """
    output_dir = Path(output_dir)
    if not output_dir.is_dir():
        raise FileNotFoundError(f"Output directory does not exist: {output_dir}")

    deleted = []
    for path in sorted(output_dir.glob("*.hdf5")):
        if path.is_file():
            path.unlink()
            deleted.append(path)
            LOGGER.info("Deleted GHS-POP output: %s", path)
    return deleted


def clear_ghs_pop_index(download_dir: Path | str = DOWNLOAD_DIR):
    """Delete the GHS-POP index file and return its path if it existed."""
    download_dir = Path(download_dir)
    index_path = download_dir / GHS_POP_INDEX_FILENAME
    if index_path.is_file():
        index_path.unlink()
        LOGGER.info("Deleted GHS-POP index file: %s", index_path)
        return index_path
    return None


def clear_all_ghs_pop_files(
    download_dir: Path | str = DOWNLOAD_DIR,
    output_dir: Path | str = OUTPUT_DIR,
):
    """Clear raw GHS-POP downloads and derived HDF5 files; return deleted paths.

    Apply the file filters of ``clear_ghs_pop_downloads`` and
    ``clear_ghs_pop_outputs``. Additionally delete the cached tiling metadata 
    files. The directories and unrelated files are preserved.
    """
    if not Path(download_dir).is_dir():
        raise FileNotFoundError(f"Download directory does not exist: {download_dir}")
    if not Path(output_dir).is_dir():
        raise FileNotFoundError(f"Output directory does not exist: {output_dir}")
    
    return [clear_ghs_pop_index(download_dir)] + clear_ghs_pop_downloads(download_dir) + clear_ghs_pop_outputs(output_dir)
