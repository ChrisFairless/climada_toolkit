"""Run a small end-to-end Aqueduct river-flood example.

This script is intended to become the basis of a notebook. It keeps each
workflow step visible so that users can copy, adapt, and inspect it:

1. validate the request;
2. inspect one generated filename;
3. download or reuse the requested rasters;
4. build and subset the CLIMADA hazard for the Dominican Republic;
5. plot the first event and save the hazard to HDF5.
"""

from pathlib import Path
import matplotlib.pyplot as plt

from climada_toolkit.inputs.hazard import aqueduct_river


# This is a small, concrete example.
# See aqueduct_river.py for the available options.
def main():

    DOWNLOAD_DIR = Path("../../../data/raw")
    OUTPUT_DIR = Path("../../../data")
    HAZARD_OUTPUT_PATH = OUTPUT_DIR / "JAM_inunriver_rcp4p5_2050.hdf5"
    PLOT_OUTPUT_PATH = OUTPUT_DIR / "JAM_inunriver_rcp4p5_2050_event0.png"

    if not DOWNLOAD_DIR.exists():
        raise FileNotFoundError(f"Download directory {DOWNLOAD_DIR} does not exist: create it before continuing.")
    if not OUTPUT_DIR.exists():
        raise FileNotFoundError(f"Output directory {OUTPUT_DIR} does not exist: create it before continuing.")

    SCENARIO = "rcp4p5"
    YEAR = 2050
    GCMS = ["GFDL-ESM2M", "MIROC-ESM-CHEM"]
    RETURN_PERIODS = [25, 50]
    COUNTRY = "JAM"  # Jamaica
    BOUNDING_BOX = (-77.3, 17.5, -76.0, 18.6)

    scenario, year, gcms, return_periods, country, bounding_box = (
        aqueduct_river.validate_aqueduct_parameters(
            scenario=SCENARIO,
            year=YEAR,
            gcms=GCMS,
            return_periods=RETURN_PERIODS,
            country=COUNTRY,
            bounding_box=BOUNDING_BOX
        )
    )

    print(f"scenario={scenario}")
    print(f"year={year}")
    print(f"country={country}")
    print(f"gcms={gcms}")
    print(f"return_periods={return_periods}")

    file_paths = []
    for return_period in return_periods:
        for gcm in gcms:
            file_path = aqueduct_river.download_aqueduct_river_file(
                scenario=scenario,
                year=year,
                gcm=gcm,
                return_period=return_period,
                download_dir=DOWNLOAD_DIR,
                force=False,
            )
            file_paths.append(file_path)

    print(f"Downloaded or checked {len(file_paths)} raster files")

    hazard = aqueduct_river.create_aqueduct_river_hazard(
        download_dir=DOWNLOAD_DIR,
        scenario=scenario,
        year=year,
        gcms=gcms,
        return_periods=return_periods,
        country=country,
        bounding_box=bounding_box,
    )

    print(f"hazard type: {hazard.haz_type}")
    print(f"event count: {len(hazard.event_name)}")
    print(f"event names: {list(hazard.event_name)}")
    print(f"event frequencies: {list(hazard.frequency)}")
    print(f"hazard centroid count: {hazard.centroids.size}")

    print("Plotting event 0")
    hazard.plot_intensity(event=0)
    plt.savefig(PLOT_OUTPUT_PATH)
    plt.close()
    print(f"plot output: {PLOT_OUTPUT_PATH}")

    hazard.write_hdf5(HAZARD_OUTPUT_PATH)
    print(f"HDF5 output: {HAZARD_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
