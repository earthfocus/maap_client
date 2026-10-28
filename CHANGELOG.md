# Changelog

## 0.3.0

### Added

- Aeolus, Biomass and FLEX support next to EarthCARE: product-name parsing, data and
  registry layout, search, download, `get`, `sync`, `state`, `list` and `catalog`.
- Mission selection: `--mission`, `MAAP_MISSION`, `maap mission list|use|show`, and
  `default_mission` / `[missions.<name>]` in `config.toml`. A collection or URL
  decides the mission on its own.
- Mission filters declared per mission and generated as CLI options: EarthCARE
  `--frame` (letters A-H); Biomass `--track`, `--frame`, `--repeat-cycle`,
  `--major-cycle`. An option a mission lacks is a clear error.
- `NO_BASELINE`: products without a baseline (Biomass `MPL_ORBPRE`, Aeolus aux types
  without catalogue version, FLEX aux types) are searched, downloaded, registered and
  tracked under the baseline folder `NO_BASELINE`.
- `--format zip` / `all` / any extension, and `--product-dir` to keep each product's
  files in a folder named after it (required for Biomass individual files and for
  Aeolus `ALDUN1A_NC`).
- Typed product names (`EarthCAREName`, `AeolusName`, `BiomassName`, `FlexName`) and
  public per-field extractors in each mission module.

### Changed

- Exit codes: a search MAAP rejects (HTTP 400, e.g. an unknown collection), an
  invalid date, a time range outside the mission period, an unknown product type in
  `catalog build` and `NO_BASELINE` for a product with baselines exit 4 (do not
  retry) instead of 3. A download 403 still exits 3.
- Malformed filter values name their flag: `--frame: invalid value 'Z': must be
  letters A-H`.
- `download --max-items` caps the new files downloaded (it was ignored); day-by-day
  searches cap `--max-items` in total.
- A long range of a sparse product is searched in one paged request instead of day
  by day; `sync` without a baseline walks only the baselines with data in the range.
- `catalog build`, `list --verify` and `sync` skip the collection-wide catalogue
  versions for a product none of whose items has a version.
- A collection without searchable items yet is listed as empty instead of failing.

### Removed

Compatibility names; import each name from where it is defined:

| Removed | Use |
|---------|-----|
| `maap_client.paths.sort_by_sensing_time`, `filter_by_fields`, `filter_by_sensing_time`, `filter_by_orbit_frame` | `maap_client.filters.sort_by_sensing_time`, `filter_by_fields`, `filter_by_sensing_time`, `filter_by_orbit` (frames: `filter_by_fields` with `{"frame": [...]}`) |
| `maap_client.constants.NO_BASELINE` | `maap_client.missions.NO_BASELINE` |
| `maap_client.constants.DEDUP_PRODUCTS`, `NO_ORBIT_PRODUCTS` | `maap_client.missions.earthcare.DEDUP_PRODUCTS`, `NO_ORBIT_PRODUCTS` |
| `maap_client.utils.parse_frames` | `maap_client.missions.earthcare.parse_frames` |
| `maap_client.COLLECTIONS` | `maap_client.constants.DEFAULT_COLLECTIONS` |
| `MaapClient.search/get/sync/download_from_registry(frames=[...])` | `filters={"frame": [...]}` |
| `maap download --use-catalog` (it had no effect) | — (`maap search --use-catalog` remains) |

### Fixed

- Aeolus products named `AE1_...` are recognised.
- `paths.extract_collection` returns `None` for any URL (it returned `EarthCARE` for
  archive zip URLs).
- `maap config` applies `-d` and shows the `-c` file; `catalog build` prints the
  catalog path once.
