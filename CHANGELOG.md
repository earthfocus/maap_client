# Changelog

## 0.3.0

### Added

- Aeolus, Biomass, FLEX and CryoSat support next to EarthCARE: product-name parsing,
  data and registry layout, search, download, `get`, `sync`, `state`, `list` and
  `catalog`. CryoSat covers the Ice and Ocean L1/L2, CryoTEMPO and CryoTEMPO-EOLIS
  collections; its products whose names give no usable sensing time are dated by the
  archive day.
- Mission selection: `--mission`, `MAAP_MISSION`, `maap mission list|use|show`, and
  `default_mission` / `[missions.<name>]` in `config.toml`. A collection or URL
  decides the mission on its own.
- Mission filters declared per mission and generated as CLI options: EarthCARE
  `--frame` (letters A-H); Biomass `--track`, `--frame`, `--repeat-cycle`,
  `--major-cycle`. An option a mission lacks is a clear error.
- `--orbit-direction ascending|descending` on EarthCARE, Biomass and CryoSat (search
  only; MAAP `sat:orbit_state`).
- `--orbit` and the mission filters are checked against the collection's queryables
  before searching: one it does not declare is a clear error (exit 4).
- `NO_BASELINE`: products without a baseline (Biomass `MPL_ORBPRE`, Aeolus aux types
  without catalogue version, FLEX aux types) are searched, downloaded, registered and
  tracked under the baseline folder `NO_BASELINE`.
- `--format zip` / `all` / any extension, and `--product-dir` to keep each product's
  files in a folder named after it (required for Biomass individual files and for
  Aeolus `ALDUN1A_NC`).
- Typed product names (`EarthCAREName`, `AeolusName`, `BiomassName`, `FlexName`,
  `CryoSatName`) and
  public per-field extractors in each mission module.

### Changed

- Exit codes: a search MAAP rejects (HTTP 400, e.g. an unknown collection), an
  invalid date, a time range outside the mission period, an unknown product type in
  `catalog build` and `NO_BASELINE` for a product with baselines exit 4 (do not
  retry) instead of 3. A download 403 still exits 3.
- Malformed filter values name their flag, and exit 4 instead of argparse's 2:
  `--frame: invalid value 'Z': must be letters A-H`.
- `catalog update` / `catalog build` of all collections record an unknown
  collection and go on with the others (exit 4 at the end); one given explicitly
  stops with exit 4.
- A download URL whose baseline cannot be read is an error of that URL (exit 4 at
  the end); the other URLs are still downloaded. `sync` and `search --registry-save`
  still stop before registering it.
- `download --max-items` caps the new files downloaded (it was ignored). For
  `search`/`get`/`sync`, `--max-items` counts whole products over the range (never
  splitting a product's files), taken after sorting by sensing time.
- A long range of a sparse product is searched in one paged request instead of day
  by day; `sync` without a baseline walks only the baselines with data in the range.
- `catalog build`, `list --verify` and `sync` skip the collection-wide catalogue
  versions for a product none of whose items has a version.
- A collection without searchable items yet is listed as empty instead of failing.
- A legacy `[mission] name` in `config.toml` is matched case-insensitively and
  stored with the built-in spelling (e.g. `earthcare` -> `EarthCARE`), which names
  the data and registry folders; an unknown name is an error.
- On Python 3.10, `tomli` is now a dependency (needed to read `config.toml`).

### Removed

Compatibility names; import each name from where it is defined:

| Removed | Use |
|---------|-----|
| `maap_client.paths.sort_by_sensing_time`, `filter_by_sensing_time`, `filter_by_orbit_frame` | `maap_client.filters.sort_by_sensing_time`, `filter_by_sensing_time`, `filter_by_orbit` (frames: `filters.filter_by_fields` with `{"frame": [...]}`) |
| `maap_client.paths.EARTHCARE_DATA_URL` | `maap_client.paths.filename_to_url(filename)` (the whole URL of a product file) |
| `maap_client.constants.DEDUP_PRODUCTS`, `NO_ORBIT_PRODUCTS` | `maap_client.missions.earthcare.DEDUP_PRODUCTS`, `NO_ORBIT_PRODUCTS` |
| `maap_client.utils.parse_frames` | `maap_client.missions.earthcare.parse_frames` |
| `maap_client.COLLECTIONS` | `maap_client.constants.DEFAULT_COLLECTIONS` |
| `MaapClient.search/get/sync/download_from_registry(frames=[...])` | `filters={"frame": [...]}` |
| `MaapSearcher.search_urls/search_urls_iter_day/search_urls_by_orbit(frames=[...])` | `extra={"frame": [...]}` (in `search_urls_by_orbit` the 4th positional argument is now `baseline`) |
| `MaapSearcher.search_baselines(candidates=None, catalog_manager=...)` | `candidates` is required |
| `maap download --use-catalog` (it had no effect) | — (`maap search --use-catalog` remains) |

### Fixed

- Aeolus products named `AE1_...` are recognised.
- The FLEX baseline is read from local data paths as well as archive URLs.
- `paths.extract_collection` returns `None` for any URL (it returned `EarthCARE` for
  archive zip URLs).
- `maap config` applies `-d` and shows the `-c` file; `catalog build` prints the
  catalog path once.
