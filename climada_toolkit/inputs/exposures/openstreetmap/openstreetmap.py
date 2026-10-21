"""Load critical infrastructure exposures using osm-flex's presets."""

import logging
from pathlib import Path

from climada.util.config import CONFIG
from climada.entity import Exposures
import osm_flex


LOGGER = logging.getLogger(__name__)

# Default file storage settings
# We use subfolders within the local storage set in climada's config file
# See https://climada-python.readthedocs.io/en/latest/development/Guide_Configuration.html#configuration
CLIMADA_DATA_DIR = CONFIG.local_data.system.dir()
DOWNLOAD_DIR = CLIMADA_DATA_DIR / "exposures" / "openstreetmap_raw"
OUTPUT_DIR = CLIMADA_DATA_DIR / "exposures" / "openstreetmap_hdf5"


# This is a wrapper around the osm-flex tools with the same functionality
# See https://github.com/osm-flex/osm-flex

def load_osm_critical_infra(
    country: str,
    ci_type: str,
    osm_path: Path | str = None,
    download_dir: Path | str = DOWNLOAD_DIR,
    output_dir: Path | str = OUTPUT_DIR,
    output_filename: str | None = None,
    overwrite: bool = False,
    **kwargs
):
    """
    Loads critical infrastructure features as calculated by the osm-flex 
    package.

    ``country`` is the ISO alpha-3 code of the country to load OSM data for.

    ``ci_type`` is the type of critical infrastructure to load. One of 
    'education', 'healthcare', 'water', 'telecom', 'road', 'rail', 'air', 'gas', 
    'oil', 'power', 'wastewater', 'food'. See the osm-flex documentation for 
    details on each type and how to customise the queries.

    ``download_dir`` is the directory to download or load the OSM PBF file from.

    ``output_dir`` is the directory where the processed exposure file will be 
    saved.

    ``output_filename`` is the name of the processed exposure file. If ``None``,
    a default filename will be generated based on the critical infrastructure 
    type.

    ``overwrite`` indicates whether to overwrite existing downloaded or 
    processed files.

    ``**kwargs`` are optional values passed to the CLIMADA Exposures 
    constructor, and can be  ``description``, ``ref_year`` or ``value_unit``.


    Returns a CLIMADA Exposures object containing the extracted geometries and
    tags. Exposure values are not assigned automatically.
    """
    # Create output directories
    Path(download_dir).mkdir(parents=False, exist_ok=True)
    Path(output_dir).mkdir(parents=False, exist_ok=True)

    # Return output file if it already exists
    if output_filename is None:
        output_filename = f"osm_{country}_{ci_type}.hdf5"
    output_path = Path(output_dir) / output_filename
    if output_path.is_file() and not overwrite:
        LOGGER.info("Using existing output file: %s", output_path)
        return Exposures.from_hdf5(output_path)

    # Download the OSM PBF file for the specified country
    download_path = osm_flex.download.get_country_geofabrik(
        country.upper(),
        file_format="pbf",
        save_path=download_dir,
        overwrite=overwrite,
    )

    # Extract critical infrastructure features
    features = osm_flex.extract.extract_cis(
        osm_path=download_path,
        ci_type=ci_type
    )
    features = features.to_crs(epsg=4326)
    
    # Create an Exposures object
    exp = Exposures(features, **kwargs)

    # Save it to file and return
    exp.write_hdf5(output_path)
    return exp



# Functions to clear cached OSM files (downloads and outputs)
# ----------------------------------------------------------

def clear_osm_downloads(download_dir: Path | str = DOWNLOAD_DIR):
    """Delete cached ``*.osm.pbf`` snapshots and return their paths.
    """
    download_dir = Path(download_dir)
    if not download_dir.is_dir():
        raise FileNotFoundError(f"Download directory does not exist: {download_dir}")

    deleted = []
    for path in sorted(download_dir.glob("*.osm.pbf")):
        if path.is_file():
            path.unlink()
            deleted.append(path)
            LOGGER.info("Deleted OSM download: %s", path)
    return deleted


def clear_osm_outputs(output_dir: Path | str = OUTPUT_DIR):
    """Delete created ``*.hdf5`` exposures and return their paths.

    Remove every HDF5 file directly within the existing output directory,
    including custom filenames.
    """
    output_dir = Path(output_dir)
    if not output_dir.is_dir():
        raise FileNotFoundError(f"Output directory does not exist: {output_dir}")

    deleted = []
    for path in sorted(output_dir.glob("*.hdf5")):
        if path.is_file():
            path.unlink()
            deleted.append(path)
            LOGGER.info("Deleted OSM output: %s", path)
    return deleted


def clear_all_osm_files(
    download_dir: Path | str = DOWNLOAD_DIR,
    output_dir: Path | str = OUTPUT_DIR,
):
    """Clear raw OSM snapshots and derived HDF5 files; return deleted paths.
    """
    return clear_osm_downloads(download_dir) + clear_osm_outputs(output_dir)
