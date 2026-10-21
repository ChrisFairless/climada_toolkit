# OpenStreetMap Exposures

This is a wrapper around the [osm-flex](https://github.com/osm-flex/osm-flex) package for quickly accessing key Exposures types from OpenStreetMap.

This only gives the basic functionality for accessing critical infrastructure data types ('education', 'healthcare', 'water', 'telecom', 'road', 'rail', 'air', 'gas', 'oil', 'power', 'wastewater', 'food'). For anything more complex, the osm-flex package gives a powerful interface for selecting exactly what you want. See the [osm-flex tutorial](https://osm-flex.readthedocs.io/en/latest/0_basic_usage.html).

Note that if you create Exposures that contain lines or polygons, you will need to use CLIMADA's `climada.util.lines_polys_handler` module to calculate impacts. See also: [an example with OpenStreetMap data](https://climada-python.readthedocs.io/en/stable/user-guide/climada_entity_Exposures_osm.html) and the [full tutorial on lines and polygons in CLIMADA](https://climada-python.readthedocs.io/en/stable/user-guide/climada_entity_Exposures_polygons_lines.html).

## Technical notes

Read these if you run into issues or want to improve performance.

- **Check the outputs!** OpenStreetMap can sometimes be **incomplete or unpredictable**. Write the Exposures' GeoDataFrame to file (TODO: helper function for this) and visualise it in GIS software to check for missing or duplicated information.
- **Some of the downloads group countries or split countries into subsets:** In the underlying OSM GeoFabrik download data, some countries are grouped together (e.g. The Gambia and Senegal) and some are split up (e.g. 'European' and 'Asian' Russia).
    - See the [osm-flex config.py](https://github.com/osm-flex/osm-flex/blob/main/src/osm_flex/config.py) for information on which countries are affected.
    - If you need to subset to a particular country, use `climada_toolkit.helpers.clip_exposures.clip_to_country`.
    - If you need to combine exposures use `Exposures.concat`.
- **Reducing resulting file sizes:** You'll often end up with a huge set of Exposures with way more detail than you need for your risk analysis. You don't often need a level of detail much higher than the Hazard data you're working with. In this case, we recommend either rasterising the Exposure data (using GIS software for now, this is a TODO) or mapping the Exposures directly to hazard Centroids, then grouping and summing them to create a simplified object (TODO: write an example of this).
- **Removing duplicate Exposures:** Sometimes OSM provides the same data twice, e.g. as a point and a polygon. There are built-in methods to handle some of the easier-to-spot cases, [described here](https://osm-flex.readthedocs.io/en/latest/2_simplifications.html).
- **Out of date information:** Existing processed files and downloads are reused. Use `overwrite=True` to refresh both the downloaded data and the processed exposure.
- **Consistent save directory:** By default this package saves the downloads in a data directory specified by CLIMADA's configuration. This is different to the default location used by osm-flex, which is at ~/osm/osm_bpf. If you're using osm-flex elsewhere, you may want to change the `DOWNLOAD_DIR` parameter in the scripts to avoid duplicate downloads.
