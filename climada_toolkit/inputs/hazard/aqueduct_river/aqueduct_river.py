"""Download, subset, and load Aqueduct river-flood hazard maps.

The functions in this module provide a small, copy-pasteable workflow:
validate a request, build Aqueduct filenames, download the requested rasters,
construct a CLIMADA ``Hazard`` object, and optionally save it as HDF5.
"""

import logging
from pathlib import Path
import numpy as np
from shapely.geometry import box

from climada.util.config import CONFIG
from climada.hazard import Hazard
from climada.util import coordinates as u_coord
from climada.util import files_handler as u_fh


LOGGER = logging.getLogger(__name__)

# Aqueduct download URLs moved from the old WRI S3 location below to this base:
# Old URL base: https://wri-projects.s3.amazonaws.com/AqueductFloodTool/download/v2/
AQUEDUCT_BASE_URL = "https://aqueduct.wridata.org/AqueductFloods20/"

AQUEDUCT_SCENARIOS = ["historical", "rcp4p5", "rcp8p5"]
AQUEDUCT_YEARS_HISTORICAL = [1980]
AQUEDUCT_YEARS_FUTURE = [2030, 2050, 2080]
AQUEDUCT_GCMS_HISTORICAL = ["WATCH"]
AQUEDUCT_GCMS_FUTURE = [
    "NorESM1-M",
    "GFDL-ESM2M",
    "HadGEM2-ES",
    "IPSL-CM5A-LR",
    "MIROC-ESM-CHEM",
]
AQUEDUCT_RETURN_PERIODS = [2, 5, 10, 25, 50, 100, 250, 500, 1000]

# Download and output paths
# We use the climada configuration to get a local data system folder.
DOWNLOAD_DIR = CONFIG.local_data.system.dir() / "hazard" / "aqueduct_river" / "raw"
OUTPUT_DIR = CONFIG.local_data.system.dir() / "hazard" / "aqueduct_river" / "hdf5"

# Global extent: use this to get a global hazard
GLOBAL_BOUNDS = (-180, -90, 180, 90)

# Create download and output directories if they do not exist (and the user has specified a CLIMADA data folder)
if CONFIG.local_data.system.dir().is_dir():
    if not DOWNLOAD_DIR.is_dir():
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    if not OUTPUT_DIR.is_dir():
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_aqueduct_river_flood(
        scenario: str,
        year: int,
        gcms: list[str] | None = None,
        return_periods: list[int] | None = None,
        country: str | None = None,
        bounding_box: tuple[float, float, float, float] | None = None,
        download_dir: Path = DOWNLOAD_DIR,
        output_dir: Path = OUTPUT_DIR,
        output_filename: str = None,
        force_redownload: bool = False,
    ):
    """Download, subset, and load Aqueduct river flood data as a CLIMADA Hazard. 
    
    This validates the request, downloads the Aqueduct GeoTIFFs (if required), 
    constructs a CLIMADA ``Hazard``, and optionally writes the
    result to HDF5. At least one of ``country`` or ``bounding_box`` must be
    supplied. Supplying both clips the exact country geometry to the supplied
    bounding box; supplying only ``bounding_box=GLOBAL_BOUNDS`` creates a global
    hazard.

    Parameters
    ----------
    scenario : str
        One of ``historical``, ``rcp4p5``, or ``rcp8p5``.
    year : int
        Historical data use 1980; future scenarios use 2030, 2050, or 2080.
    gcms : list of str, optional
        General circulation models to use. None or an empty list selects all available GCMs for the scenario.
    return_periods : list of int, optional
        Return periods to include. None or an empty list selects all available return periods. The output sorts by 
        lowest to highest return period.
    country : str, optional
        ISO3 country code. At least one of ``country`` or ``bounding_box`` must be supplied.
    bounding_box : tuple of float, optional
        Bounding box as (min_lon, min_lat, max_lon, max_lat). At least one of ``country`` or ``bounding_box`` must be supplied.
    download_dir : pathlib.Path, optional
        Directory to download Aqueduct GeoTIFFs to.
    output_dir : pathlib.Path, optional
        Directory for the HDF5 output. Must already exist. Defaults to OUTPUT_DIR.
    output_filename : str
        HDF5 filename, combined with output_dir to form the output path. Not specifying this will skip writing to HDF5.
    force_redownload : bool, optional
        Download files again even if they already exist. Defaults to False.

    Returns
    -------
    climada.hazard.Hazard
        The constructed river flood hazard.
    """
    
    # Validate and normalize input parameters
    # ---------------------------------------
    scenario, year, gcms, return_periods, country, bounding_box = (
        validate_aqueduct_parameters(
            scenario, year, gcms, return_periods, country, bounding_box
        )
    )

    if output_dir is not None:
        if not Path(output_dir).is_dir():
            raise FileNotFoundError(
                f"Output directory does not exist: {Path(output_dir)}"
            )


    # Download required Aqueduct GeoTIFFs
    # ---------------------------------------
    for rp in return_periods:
        for gcm in gcms:
            download_aqueduct_river_file(
                scenario=scenario, year=year, gcm=gcm, return_period=rp,
                download_dir=download_dir, force_redownload=force_redownload,
            )

    # Create the hazard object for the area of interest
    # ---------------------------------------
    hazard = create_aqueduct_river_hazard(
        download_dir=download_dir,
        scenario=scenario,
        year=year,
        gcms=gcms,
        return_periods=return_periods,
        country=country,
        bounding_box=bounding_box,
    )

    # Save the Hazard to HDF5
    # ---------------------------------------
    if output_filename is not None:
        output_path = Path(output_dir) / output_filename
        hazard.write_hdf5(output_path)
        LOGGER.info(
            "Wrote Aqueduct hazard to %s (%.2f MiB)",
            output_path, output_path.stat().st_size / 1024**2,
        )

    return hazard


def download_aqueduct_river_file(
        scenario: str,
        year: int,
        gcm: str,
        return_period: int,
        download_dir: Path | str = DOWNLOAD_DIR,
        force_redownload: bool = False,
    ):
    """Download the requested Aqueduct river-flood GeoTIFFs (if missing).

    Existing files in ``download_dir`` are not overwritten, unless ``force_redownload`` is 
    True. The download directory must already exist.

    Returns
    -------
    pathlib.Path
        Local path to the file on disk.
    """

    scenario, year, gcms, return_periods, _, _ = validate_aqueduct_parameters(
        scenario=scenario,
        year=year,
        gcms=[gcm],
        return_periods=[return_period],
        require_geometry=False,
    )
    download_dir = Path(download_dir)
    if not download_dir.is_dir():
        raise FileNotFoundError(f"Download directory does not exist: {download_dir}")

    filename = build_aqueduct_river_filename(scenario, year, gcm, return_period)
    
    url = f"{AQUEDUCT_BASE_URL}{filename}"
    file_path = download_dir / filename

    if file_path.exists() and not force_redownload:
        LOGGER.info(
            "Aqueduct file already downloaded: scenario=%s year=%s gcm=%s rp=%s "
            "url=%s local_path=%s size=%.2f MiB",
            scenario, year, gcm, return_period, url, file_path,
            file_path.stat().st_size / 1024**2,
        )
        return file_path

    LOGGER.info(
        "Downloading Aqueduct file: scenario=%s year=%s gcm=%s rp=%s "
        "url=%s local_path=%s",
        scenario, year, gcm, return_period, url, file_path,
    )
    try:
        u_fh.download_file(url, download_dir=download_dir)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to download {filename} from {url}"
        ) from exc
    LOGGER.info(
        "Downloaded Aqueduct file: local_path=%s size=%.2f MiB",
        file_path, file_path.stat().st_size / 1024**2,
    )
    return file_path


def create_aqueduct_river_hazard(
        download_dir: str | Path,
        scenario: str,
        year: int,
        gcms: list[str] | None = None,
        return_periods: list[int] | None = None,
        country: str | None = None,
        bounding_box: tuple[float, float, float, float] | None = None,
    ):
    """Create a river flood Hazard object by return period.

    The download directory must already have the required Aqueduct river-flood 
    GeoTIFFs. The result is a CLIMADA ``Hazard`` with ``haz_type="RF"`` and 
    intensity units of metres. Event frequencies adjusted so that return periods
    correspond to Aqueduct return periods exceedance probabilities are 
    calculated (see comment in the code).

    If ``country`` is supplied, its land geometry is used. If
    ``bounding_box`` is supplied, the data are clipped to the box. Both can be 
    used together.
    
    If ``gcms`` is None or empty, all available GCMs are used. If
    ``return_periods`` is None or empty, all available return periods are used.
    Events are ordered by ascending return period, then by the supplied GCM order.

    Returns
    -------
    climada.hazard.Hazard
        The constructed Hazard object.
    """

    scenario, year, gcms, return_periods, country, bounding_box = (
        validate_aqueduct_parameters(
            scenario, year, gcms, return_periods, country, bounding_box
        )
    )

    # Construct the geometry of interest
    # ----------------------------------
    if country is not None:
        country_geometry = list(u_coord.get_land_geometry([country]).geoms)
        if bounding_box is None:
            geometry = country_geometry
        else:
            clip_box = box(*bounding_box)
            geometry = [
                part.intersection(clip_box)
                for part in country_geometry
                if not part.intersection(clip_box).is_empty
            ]
    else:
        geometry = [box(*bounding_box)]


    # Convert return periods to event frequencies
    # ----------------------------------
    # This conversion is necessary so that the _cumulative frequency_ of events
    # matches the return periods, rather than the individual event frequencies
    return_periods_sorted = sorted(return_periods)  # ascending
    exceedance_frequency = 1 / np.array(return_periods_sorted, dtype=float)
    event_frequency = exceedance_frequency - np.append(exceedance_frequency[1:], 0)

    event_frequency = event_frequency / len(gcms)  # Divide by the number of GCMs to distribute frequencies equally
        # Note: if you want to weight the GCMs differently, you can modify this division accordingly and index by RP and GCM
    event_frequency_by_rp = dict(zip(return_periods_sorted, event_frequency))


    # Create lists of file properties to use in constructing the hazard
    # ----------------------------------
    file_paths = []
    event_names = []
    frequencies = []
    for return_period in return_periods_sorted:
        for gcm in gcms:
            file_name = build_aqueduct_river_filename(scenario, year, gcm, return_period)
            file_paths.append(Path(download_dir) / file_name)
            event_names.append(f"rp{return_period}_{gcm}_{scenario}_{year}")
            frequencies.append(event_frequency_by_rp[return_period])

    LOGGER.info("Reading Aqueduct raster files: %s", file_paths)
    if not all(path.is_file() for path in file_paths):
        raise FileNotFoundError(
            "Some Aqueduct raster files are missing. "
            "Download files first with load_aqueduct_river_flood or download_aqueduct_river_file: "
            "Missing files: %s" % [str(path) for path in file_paths if not path.is_file()]
        )

    # Construct the hazard from the raw raster files
    # ----------------------------------
    hazard = Hazard.from_raster(
        files_intensity=file_paths,
        files_fraction=None,
        attrs={
            "event_id": np.arange(len(event_names)) + 1,
            "event_name": event_names,
            "frequency": frequencies,
            "unit": "m"
        },
        haz_type="RF",
        geometry=geometry,
    )
    LOGGER.info("Created Aqueduct river-flood hazard with %s events", len(event_names))

    return hazard


def build_aqueduct_river_filename(
        scenario: str,
        year: int,
        gcm: str,
        return_period: int
    ):
    """Build the filename for one Aqueduct river-flood GeoTIFF.

    The filename follows Aqueduct's published convention.
    Parameters are validated before the filename is returned.
    """

    validate_aqueduct_parameters(
        scenario=scenario,
        year=year,
        gcms=[gcm],
        return_periods=[return_period],
        require_geometry=False,
    )
    return (
        f"inunriver_{scenario}_{gcm.rjust(14, '0')}_{year}_"
        f"rp{str(return_period).rjust(5, '0')}.tif"
    )



def validate_aqueduct_parameters(
    scenario: str,
    year: int,
    gcms: list[str] | None = None,
    return_periods: list[int] | None = None,
    country: str | None = None,
    bounding_box: tuple[float, float, float, float] | None = None,
    require_geometry: bool = True,
):
    """Validate and normalize an Aqueduct river-flood request.

    Parameters
    ----------
    scenario : str
        One of ``historical``, ``rcp4p5``, or ``rcp8p5``.
    year : int
        Historical data use 1980; future scenarios use 2030, 2050, or 2080.
    gcms : list[str], optional
        Requested GCMs. If None or empty, all GCMs valid for ``scenario`` are used.
    return_periods : list[int], optional
        Requested return periods. If None or empty, all supported return periods are
        used.
    country : str, optional
        ISO3 country code. If supplied with ``bounding_box``, the country geometry
        is intersected with the bounding box.
    bounding_box : tuple[float, float, float, float], optional
        ``(min_lon, min_lat, max_lon, max_lat)``. Required unless ``country`` is
        supplied. ``GLOBAL_BOUNDS`` can be passed explicitly for a global hazard.
    require_geometry : bool, default=True
        Require ``country`` or ``bounding_box``. Set to ``False`` for download-only
        validation, where no spatial subset is needed.

    Returns
    -------
    tuple
        Normalized ``(scenario, year, gcms, return_periods, country, bounding_box)``.

    Raises
    ------
    ValueError
        If a parameter is unsupported, inconsistent, duplicated, or missing.
    """

    # Validate scenario and year
    if not isinstance(year, (int, np.integer)):
        raise ValueError("year must be an integer")
    if scenario not in AQUEDUCT_SCENARIOS:
        raise ValueError(f"Invalid Aqueduct scenario: {scenario}. Must be one of {', '.join(AQUEDUCT_SCENARIOS)}")
    if year not in AQUEDUCT_YEARS_HISTORICAL + AQUEDUCT_YEARS_FUTURE:
        raise ValueError(f"Invalid Aqueduct year: {year}. Must be one of {', '.join(AQUEDUCT_YEARS_HISTORICAL + AQUEDUCT_YEARS_FUTURE)}")
    if scenario == "historical" and year not in AQUEDUCT_YEARS_HISTORICAL:
        raise ValueError("Historical Aqueduct data requires year 1980")
    if scenario != "historical" and year not in AQUEDUCT_YEARS_FUTURE:
        raise ValueError(f"Future Aqueduct scenarios require one of the following years: {', '.join(map(str, AQUEDUCT_YEARS_FUTURE))}")

    valid_gcms = (
        AQUEDUCT_GCMS_HISTORICAL
        if scenario == "historical"
        else AQUEDUCT_GCMS_FUTURE
    )

    # If no GCMs are provided, use all available GCMs
    if gcms is None or len(gcms) == 0:
        gcms = list(valid_gcms)
    else:
        gcms = list(gcms)
    
    # Validate GCMs
    if len(gcms) != len(set(gcms)):
        raise ValueError("GCMs must not contain duplicates")
    invalid_gcms = [gcm for gcm in gcms if gcm not in valid_gcms]
    if invalid_gcms:
        raise ValueError(
            f"Invalid GCMs for {scenario}: {', '.join(invalid_gcms)}. Valid GCMs for {scenario} scenario: {', '.join(valid_gcms)}"
        )

    # If no return periods are provided, use all of them
    if return_periods is None or len(return_periods) == 0:
        return_periods = list(AQUEDUCT_RETURN_PERIODS)
    else:
        return_periods = list(return_periods)

    # Validate return periods
    if not all(isinstance(rp, (int, np.integer)) for rp in return_periods):
        raise ValueError("return_periods must contain integers")
    if len(return_periods) != len(set(return_periods)):
        raise ValueError("Return periods must not contain duplicates")
    invalid_rps = [rp for rp in return_periods if rp not in AQUEDUCT_RETURN_PERIODS]
    if invalid_rps:
        raise ValueError(f"Invalid Aqueduct return periods: {invalid_rps}. Valid return periods: {', '.join(map(str, AQUEDUCT_RETURN_PERIODS))}")
    return_periods = sorted(int(rp) for rp in return_periods)

    # Validate geometry requirements
    if require_geometry and country is None and bounding_box is None:
        raise ValueError("Provide a country ISO3 code or bounding_box")
    if country is not None:
        if not isinstance(country, str) or len(country) != 3:
            raise ValueError("country must be one ISO3 country code")
        country = country.upper()
    if bounding_box is not None:
        if len(bounding_box) != 4:
            raise ValueError("bounding_box must contain four values")
        min_lon, min_lat, max_lon, max_lat = bounding_box
        if not (-180 <= min_lon < max_lon <= 180 and -90 <= min_lat < max_lat <= 90):
            raise ValueError("boundary longitudes must be within -180 and 180 and latitudes within -90 and 90")

    return scenario, year, gcms, return_periods, country, bounding_box
