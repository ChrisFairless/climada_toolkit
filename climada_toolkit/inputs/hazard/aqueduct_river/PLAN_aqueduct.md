## Plan: Aqueduct River-Flood Toolkit Specification

We are designing a simple, copy-paste-friendly Aqueduct river-flood toolkit. The approach combines the reusable parts of the CLIMADA Petals loader with the Gambia batch workflow, while keeping configuration visible and avoiding unnecessary abstractions.

**Decisions so far**

1. **Overall structure: layered functions plus a convenience workflow**
	- Use ordinary functions and cohesive code blocks rather than an `AqueductRiverFloodSpec` class.
	- Keep download, hazard construction, and persistence logic independently understandable and reusable where that does not add complexity.
	- Provide a simple high-level workflow for the common case, composed from the lower-level functions.
	- Preserve copy-pasteability: conceptual code should remain together in the file that uses it.

2. **Configuration style: hard-coded, user-editable variables**
	- Put environment and dataset configuration near the top of the file.
	- Do not require users to edit class functionality to adapt the example.
	- Define all supported options in visible constants:
	  - `AQUEDUCT_SCENARIOS`
	  - `AQUEDUCT_YEARS_HISTORICAL`
	  - `AQUEDUCT_YEARS_FUTURE`
	  - `AQUEDUCT_GCMS_HISTORICAL`
	  - `AQUEDUCT_GCMS_FUTURE`
	  - `AQUEDUCT_RETURN_PERIODS`
	  - `DOWNLOAD_DIR`
	  - `OUTPUT_DIR`
	  - `GLOBAL_BOUNDS`
	- Do not define defaults for scenario or year. If `gcms` is omitted, select all GCMs valid for the selected scenario: `AQUEDUCT_GCMS_HISTORICAL` for historical and `AQUEDUCT_GCMS_FUTURE` for future scenarios.
	- If `return_periods` is omitted, use all `AQUEDUCT_RETURN_PERIODS`.
	- Set `DOWNLOAD_DIR = Path("./data/raw")` and `OUTPUT_DIR = Path("./data")`.
	- Define `GLOBAL_BOUNDS = (-180, -90, 180, 90)` and pass it explicitly for a global hazard.
	- Add a comment recommending that these paths be set relative to CLIMADA's `CONFIG.local_data.system` location.
	- Define user-set defaults separately and allow the defaults to be overridden by function parameters.
	- Avoid adding packages that are not already used in CLIMADA.

3. **Download behavior: on-demand download**
	- The main loader downloads missing Aqueduct GeoTIFFs automatically.
	- Existing local files are reused.
	- Downloading should use the existing CLIMADA file-download utility where practical.
	- Source URL and local directories remain visible and editable.
	- Raise immediately on download failure with the filename and URL; do not construct a partial hazard.

4. **Metadata and logging: no metadata CSV**
	- Do not write an `aqueduct_download_metadata.csv` file.
	- Return only the generated hazard object.
	- Log useful per-file metadata instead, including scenario, year, GCM, return period, URL, local path, and whether the file was downloaded or reused.
	- Use logging for requested files, downloads, reuse, processing, and output/persistence steps.

5. **Parameterization and combination rules**
	- `scenario`: exactly one selection per call.
	- `year`: exactly one selection per call.
	- `gcms`: one or more selections.
	- `return_periods`: one or more selections.
	- Multiple selected GCMs and return periods are combined into one hazard.
	- Scenarios and years are not silently combined; users make separate calls for those dimensions.
	- Require at least one of `country` or `bounding_box`; allow both to be specified.
	- If both are supplied, intersect the exact CLIMADA land geometry with the bounding box before raster loading.
	- If only `country` is supplied, use its exact CLIMADA land geometry.
	- If only `bounding_box` is supplied, use the bounding box itself; callers may pass `GLOBAL_BOUNDS` explicitly for a global hazard.

6. **Combined-GCM frequency handling: follow Gambia implementation (option A)**
	- Compute return-period event frequencies as differences in exceedance probabilities, following the Gambia workflow.
	- When multiple GCMs are combined, divide each event frequency equally by the number of selected GCMs.
	- Keep model-specific events rather than averaging raster intensities.
	- Validate that frequencies are positive and that the combined frequencies retain the expected total for the selected return-period distribution.

7. **Filename generation and validation: explicit validation plus a reusable builder (options A+C)**
	- Keep filename construction in a small, independently reusable function.
	- Validate all known Aqueduct combinations before downloading:
	  - `historical` requires year `1980` and GCM `WATCH`.
	  - `rcp4p5` and `rcp8p5` require supported future years.
	  - Future scenarios require one of the supported future GCMs.
	  - Return periods must be among the standard Aqueduct return periods.
	- Raise a clear `ValueError` before any download when a combination is invalid.
	- Keep filename generation and validation readable and visible for copy-paste users.
	- Supported years are `1980`, `2030`, `2050`, and `2080`; historical uses `1980`/`WATCH`, and future scenarios use the five future GCMs.
	- Reject duplicate GCMs and return periods, reject empty selections, and validate without mutating caller-provided lists.

8. **Geographic selection and clipping: optional country intersected with optional bounds**
	- Accept both an optional ISO3 `country` and optional `bounding_box=(min_lon, min_lat, max_lon, max_lat)`.
	- Require at least one of `country` or `bounding_box`, while allowing both.
	- Use exact CLIMADA land geometry alone for a country-only request.
	- Intersect exact CLIMADA land geometry with the bounding box when both are supplied.
	- Use the bounding box alone for a bounds-only request; pass `GLOBAL_BOUNDS` explicitly for global output.
	- Do not derive the clipping extent from LitPop in the initial implementation.
	- Allow country and bounding_box to be specified together; the bounding box is applied first and country geometry is intersected with it.

9. **Hazard construction: generic CLIMADA Hazard with river-flood type (option B, with `RF`)**
	- Construct the output with core CLIMADA's generic `Hazard.from_raster`.
	- Set `haz_type="RF"` so the object is labelled consistently as a river-flood hazard.
	- Set `hazard.units = "m"` because Aqueduct river-flood intensities are flood depths in metres.
	- Do not make the hazard class a user parameter in the initial implementation.
	- Keep the implementation usable without requiring the specialized Petals `RiverFlood` class.

10. **Event naming and ordering: descriptive names with compact return periods (option B variant)**
	- Use names such as `rcp4p5_2050_GFDL-ESM2M_rp100` so each event remains self-describing.
	- Use `rp{N}` rather than the longer `1-in-{N}y` format.
	- Preserve the user-provided GCM order; do not alphabetically or otherwise sort GCMs.
	- Sort return periods in descending order.
	- Create events in return-period-first order, with GCMs ordered according to the user input within each return period.
	- Calculate frequencies in the same descending return-period order, avoiding a separate reorder step.
	- Assign sequential integer event IDs independently of event names.

11. **Output and persistence: optional HDF5 path (option C)**
	- Always return the in-memory hazard object.
	- If the caller supplies `output_path`, write the hazard to HDF5 at that path.
	- If no output path is supplied, do not write a file.
	- Do not create directories automatically; check required directories at the start of execution and raise clearly if they do not exist.
	- Log the output path when persistence is requested.

12. **Supported backend scope: Aqueduct only initially (option A)**
	- Keep the first implementation focused exclusively on Aqueduct river-flood GeoTIFFs.
	- Do not add a source/backend parameter or generalize for ISIMIP, JRC, GloFAS, or other datasets yet.
	- Future data sources can be added as separate snippets or later extensions once a concrete use case exists.

13. **Validation and testing: light default tests plus notebook-driven integration (option C)**
	- Keep the default test suite light and offline, including import/configuration checks.
	- Use a notebook as the live integration test and run it as part of notebook discovery/execution.
	- Put the integration notebook in the same folder as the Aqueduct module/script.
	- Use the concrete integration selection: `scenario="rcp4p5"`, `year=2050`, `gcms=["GFDL-ESM2M", "MIROC-ESM-CHEM"]`, `return_periods=[2, 5]`, and `country="DOM"`.
	- Write downloads under `DOWNLOAD_DIR` and generated HDF5 output under `OUTPUT_DIR`.
	- The notebook should call the public sub-methods one by one, print logging output containing metadata and paths, construct the hazard, call `Hazard.plot_intensity(0)`, and save the hazard with `Hazard.write_hdf5()`.
	- Verify generated files, hazard type, event count and names, frequencies, and spatial/hazard output through notebook assertions or visible outputs.
	- Do not make ordinary unit/import checks depend on network access; the notebook integration run is intentionally network-aware.
	- Superseded: execute notebooks in CI via `pytest --nbmake` rather than a shell script calling `jupyter nbconvert` directly (see decision below); `nbmake` still runs notebooks out-of-place and does not mutate source notebooks.

14. **Packaging and documentation: one importable module plus an integration notebook (option A)**
	- Keep the implementation in `data_sources/hazard/aqueduct.py` so users can import it.
	- Keep configuration, filename generation, validation, downloading, hazard construction, logging, and optional persistence understandable within that module.
	- Expose only five public functions initially: `validate_aqueduct_parameters`, `aqueduct_river_filename`, `download_aqueduct_river_files`, `create_aqueduct_river_hazard`, and `load_aqueduct_river_flood`.
	- `download_aqueduct_river_files` returns a list of local `Path` objects for downloaded or reused files.
	- Add a notebook that demonstrates the complete workflow by calling the sub-methods sequentially.
	- Treat notebook discovery and execution as the primary integration-testing mechanism for external dependencies.
	- Avoid duplicating the implementation in a separate script.

**Questions already considered**

- Should the toolkit be a class, separate functions, one high-level method, or layered functions plus a wrapper? **Answered: layered functions plus a convenience workflow, without a specification class.**
- Should downloads be explicit or automatic? **Answered: automatic download of missing files.**
- Should the loader return metadata as well as the hazard? **Answered: return only the hazard; use logging instead of a metadata CSV.**
- What should plural parameters mean? **Answered: only GCMs and return periods may be plural and are combined; scenario and year are singular.**
- How should multiple GCM frequencies be handled? **Answered: divide frequencies equally among GCMs, following Gambia.**
- How should filenames and parameter combinations be handled? **Answered: validate all known combinations before downloading and expose filename generation as a separate reusable function.**
- How should geographic selection and clipping work? **Answered: accept both optional country and bounds; default bounds to `GLOBAL_BOUNDS`, then intersect exact CLIMADA country geometry with the box when a country is supplied.**
- How should the hazard object be constructed? **Answered: use core CLIMADA `Hazard.from_raster` with `haz_type="RF"`; do not require the Petals `RiverFlood` class.**
- How should event names and ordering work? **Answered: use descriptive names with `rp{N}`, preserve user-provided GCM order, sort return periods decreasingly, and use return-period-first ordering.**
- How should output persistence work? **Answered: always return the hazard; write HDF5 only when an optional `output_path` is supplied, without creating directories.**
- What data-source scope should the first version support? **Answered: Aqueduct river-flood GeoTIFFs only; do not generalize to other backends yet.**
- What should the parameter defaults be? **Answered: scenario and year are required; omitted GCMs select all GCMs valid for the selected scenario; omitted return periods select all supported return periods.**
	- What should the implementation defaults and filesystem layout be? **Answered: use repository-relative `DOWNLOAD_DIR=./data/raw` and `OUTPUT_DIR=./data`, recommend configuring them relative to `CONFIG.local_data.system`, and check both directories exist at startup.**
- What testing approach should the first version use? **Answered: light offline default tests plus a notebook-driven live integration workflow using the explicit DOM example above.**
- What should notebook execution use? **Superseded: originally a shell runner calling `jupyter nbconvert`; changed to `pytest --nbmake` so notebook execution reuses the pytest/JUnit reporting already used for CI, at the cost of adding the `nbmake` dependency.**
- Where should the implementation and integration example live? **Answered: keep the implementation in one importable module, `data_sources/hazard/aqueduct.py`, and use a notebook as the integration test.**

**Next discussion sequence**

The design questions are resolved. The remaining implementation work is to create the importable module, the adjacent integration notebook, and the temporary-directory notebook runner.

**Scope bounding_box**

- Initial scope is Aqueduct river flood only.
- Coastal flood, ISIMIP, JRC, GloFAS, and other hazards are excluded from this specification round.
- Keep implementation readable and laptop-friendly; optimize only if the dataset scale requires chunking.
- Testing remains light and integration-focused; the notebook integration run is intentionally network-aware.
- Do not create missing download or output directories automatically; fail early with a clear message.

**Verification expectations**

- Confirm imports and configuration defaults work.
- Verify generated Aqueduct filenames and parameter validation.
- Exercise the notebook integration path with `rcp4p5`, 2050, GCMs `GFDL-ESM2M` and `MIROC-ESM-CHEM`, return periods `[2, 5]`, and country `DOM`.
- Verify multi-GCM frequency handling against the Gambia semantics.
- Verify event naming, return-period-first ordering, and user-provided GCM ordering.
- Check that logging records file reuse/download and hazard construction without creating a metadata CSV.
- Verify optional HDF5 output through `Hazard.write_hdf5()`.

