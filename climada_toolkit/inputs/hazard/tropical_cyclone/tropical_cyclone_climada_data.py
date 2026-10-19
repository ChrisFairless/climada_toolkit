"""Load cyclone wind hazards from the CLIMADA Data API"""

from climada.util.api_client import Client
from climada.util.constants import SYSTEM_DIR

# Convenience functions to access particular datasets
# ---------------------------------------------------

# Historic event footprints
# Note: these are not kept up to date on the CLIMADA Data API
# To include events from recent years, you will need to calculate the wind 
# footprints yourself (TO DO)
def load_tropical_cyclone_observed(
        country=None,
        dump_dir=SYSTEM_DIR
    ):
    """Return wind footprints for observed historical storms in an ISO3 country.
    country=None selects global data.
    """
    return load_tropical_cyclone(
        country=country,
        event_type="observed",
        dump_dir=dump_dir,
    )


# CLIMADA Random Walk synthetic event footprints: historic climate
def load_tropical_cyclone_historic_climate(
        country=None,
        dump_dir=SYSTEM_DIR
    ):
    """Return wind footprints for synthetic historical storms in an ISO3 country from the CLIMADA Data API.
    Using the CLIMADA Data API's random walk model for 10 synthetic storms per historic observed storm.
    """
    return load_tropical_cyclone(
        country=country,
        event_type="synthetic",
        climate_scenario="None",
        model_name="random_walk",
        dump_dir=dump_dir
    )


# CLIMADA Random Walk synthetic event footprints: future climate
def load_tropical_cyclone_future_climate(
        country=None,
        climate_scenario=None,
        ref_year=None,
        dump_dir=SYSTEM_DIR
    ):
    """Return wind footprints for synthetic future storms in an ISO3 country from the CLIMADA Data API.
    Using the CLIMADA Data API's random walk model for 10 synthetic storms per historic observed storm, with 
    frequencies weighted according to the specified climate scenario.
    
    country: str, optional
        ISO3 country code. None selects global data.
    climate_scenario: str, optional
        Climate scenario for the future climate. One of "rcp45", "rcp60", "rcp85".
    ref_year: int, optional
        Reference year for the future climate scenario. One of 2040, 2060, 2080.
    """
    return load_tropical_cyclone(
        country=country,
        event_type="synthetic",
        climate_scenario=climate_scenario,
        ref_year=ref_year,
        model_name="random_walk",
        dump_dir=dump_dir
    )


# Generic loader for tropical cyclone datasets from the CLIMADA Data API
# ----------------------------------------------------------------------

def load_tropical_cyclone(
    country: str=None,
    event_type: str=None,
    climate_scenario: str=None,
    ref_year: int=None,
    model_name: str=None,
    gcm: str=None,
    basin: str=None,
    res_arcsec: int=None,
    name: str=None,
    version: str=None,
    status: str="active",
    dump_dir: str=SYSTEM_DIR,
):
    """Load a tropical cyclone dataset from the CLIMADA Data API as a CLIMADA 
    Hazard. Variable names follow the CLIMADA Data API conventions.

    See https://climada-python.readthedocs.io/en/stable/user-guide/climada_util_api_client.html 
    for more information on the CLIMADA Data API and 
    https://climada.ethz.ch/data-api/v2/docs for detailed API documentation.

    Parameters
    ----------
    country : str, optional
        ISO3 country code. None selects a global dataset.
    event_type : str, optional
        API event type: "observed" or "synthetic".
    climate_scenario : str, optional
        API climate scenario, such as "rcp45".
    ref_year : int or str, optional
        Reference year, converted to a string for the API.
    model_name : str, optional
        Cyclone model name, using the API spelling.
    gcm : str, optional
        General circulation model name, where supported by the dataset.
    basin : str, optional
        API basin code, where supported by the dataset.
    res_arcsec : int or str, optional
        Spatial resolution in arc seconds, converted to a string for the API.
    name : str, optional
        Exact API dataset name, useful for resolving ambiguous selections.
    version : str, optional
        Dataset version. None uses the client's newest matching version.
    status : str, optional
        API dataset status. Defaults to "active".
    dump_dir : str or pathlib.Path, optional
        Download directory. Defaults to CLIMADA's SYSTEM_DIR.

    Returns
    -------
    climada.hazard.Hazard
        The API hazard, with its original events and frequencies.

    """
    properties = {
        "spatial_coverage": "global" if country is None else "country",
    }
    if country is not None:
        properties["country_iso3alpha"] = country

    for key, value in (
        ("event_type", event_type),
        ("climate_scenario", climate_scenario),
        ("ref_year", ref_year),
        ("model_name", model_name),
        ("gcm", gcm),
        ("basin", basin),
        ("res_arcsec", res_arcsec),
    ):
        if value is not None:
            properties[key] = str(value) if key in ("ref_year", "res_arcsec") else value

    return Client().get_hazard(
        "tropical_cyclone",
        name=name,
        version=version,
        properties=properties,
        status=status,
        dump_dir=dump_dir,
    )

