import requests

from climada_toolkit.inputs.hazard.aqueduct_river import build_aqueduct_river_filename, AQUEDUCT_BASE_URL


def test_aqueduct_river_file_exists_remotely():
    filename = build_aqueduct_river_filename("rcp4p5", 2050, "GFDL-ESM2M", 250)
    url = f"{AQUEDUCT_BASE_URL}{filename}"

    # HEAD checks the file is served without downloading it
    response = requests.head(url, allow_redirects=True, timeout=30)

    assert response.status_code == 200
