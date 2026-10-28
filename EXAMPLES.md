# MAAP Client Reference and Examples

Reference for the `maap` CLI and the Python library: configuration, missions, formats,
filters, on-disk layout and command examples. The [README](README.md) has the quickstart.

Most examples use EarthCARE (`EarthCAREL0L1Products_MAAP`, `CPR_NOM_1B`); the mission
sections show the Aeolus, Biomass and FLEX variants.

## Contents

- [Installation](#installation)
- [Configuration](#configuration)
- [Missions](#missions)
- [Formats](#formats)
- [Filters](#filters)
- [On-disk layout](#on-disk-layout)
- [Mission notes](#mission-notes)
- [Not supported yet](#not-supported-yet)
- [Command examples](#command-examples)
- [Common workflows](#common-workflows)
- [Reliability](#reliability)
- [Exit codes and wrapper scripts](#exit-codes-and-wrapper-scripts)
- [Python API](#python-api)
- [Troubleshooting](#troubleshooting)

---

## Installation

```bash
pip install maap-client
```

For development:

```bash
git clone https://github.com/earthfocus/maap_client.git
cd maap_client
pip install -e .
```

---

## Configuration

Run `maap config` to see the paths and the mission in use:

```
mission:           EarthCARE
mission_start:     2024-05-28T00:00:00Z
mission_end:       2045-12-31T23:59:59Z
mission_source:    config
default_formats:   h5, eof, dbl
```

### Priority

Settings are resolved in order (highest first): CLI arguments, environment variables,
the config file (`~/.maap/config.toml`, or `-c FILE`), built-in defaults.

### Environment variables

- `MAAP_DATA_DIR` - download directory
- `MAAP_CATALOG_DIR` - catalog queryables directory
- `MAAP_BUILT_CATALOG_DIR` - built catalogs directory
- `MAAP_REGISTRY_DIR` - registry (state files) directory
- `MAAP_CREDENTIALS_FILE` - credentials file path
- `MAAP_CATALOG_URL` - MAAP catalog API URL
- `MAAP_MISSION` - mission used when the collection or URLs do not decide it
- `MAAP_MISSION_START` / `MAAP_MISSION_END` - date bounds of the mission in use

### Config file

```toml
# Top-level keys come before any [table].
default_mission = "EarthCARE"          # optional

[paths]
data_dir = "/data/maap/data"
catalog_dir = "/data/maap/catalogs"
built_catalog_dir = "/data/maap/built_catalogs"
registry_dir = "/data/maap/registry"
credentials_file = "~/.maap/credentials.txt"

[api]
catalog_url = "https://catalog.maap.eo.esa.int/catalogue"
token_url = "https://iam.maap.eo.esa.int/realms/esa-maap/protocol/openid-connect/token"

# Optional overrides of a built-in mission profile ('maap mission show <name>')
[missions.Biomass]
start = "2025-01-01T00:00:00Z"
end = "2045-12-31T23:59:59Z"
collections = ["BiomassLevel1b", "BiomassAux"]   # replace the profile collections
# collections_extend = ["BiomassNewCollection"]  # or add to them
default_format = "zip"                           # used when no --format is given; or a
                                                 # priority list, e.g. ["tiff", "zip"]
```

Every collection belongs to one mission: a collection listed in two missions, or an
unknown mission name, is a configuration error (exit 4).

A legacy `[mission]` section (`name`, `start`, `end`, `collections`, `collections_extend`)
is still accepted: it is read as the overrides of the named mission and as `default_mission`.

---

## Missions

```bash
maap mission list            # known missions; the active one is marked with its source
maap mission use Biomass     # persist the active mission (~/.maap/active_mission)
maap mission show            # profile of the active mission
maap mission show FLEX       # collections, dates, default formats, filters
```

The mission is inferred from the collection (or, for `download --url/--url-file`, from
the file names). Only when nothing decides it, the order is (highest first): `--mission`
(top-level or after the sub-command; the sub-command one wins), `MAAP_MISSION`,
`maap mission use`, `default_mission` in the config (or a legacy `[mission]` name),
`EarthCARE`.

| Infer the mission from their inputs | Do not determine it (follow the order above) |
|-------------------------------------|----------------------------------------------|
| `list <collection>`, `search`, `download`, `get`, `sync`, `state show/pending/cleanup`, `catalog update/build <collection>`, `download --url/--url-file`, `state mark` (collection taken from each path) | `catalog update`, `catalog build` and `list` without a collection, `config`, `mission show` without a name |

Scripts and cron jobs should pass `--mission` or set `MAAP_MISSION` for the second group,
so a `maap mission use` typed on the same machine does not change what they do:

```bash
maap --mission Biomass catalog update
MAAP_MISSION=FLEX maap list
maap catalog build --mission Aeolus
```

| Mission | Collections (`maap mission show <name>`) | Default dates |
|---------|------------------------------------------|---------------|
| EarthCARE | `EarthCAREL0L1Products_MAAP`, `EarthCAREL1Validated_MAAP`, `EarthCAREL2Validated_MAAP`, `JAXAL2Validated_MAAP`, ... (12) | 2024-05-28 → 2045-12-31 |
| Aeolus | `AeolusBaseline16Products10`, `AeolusEOLProducts10`, `AeolusL2CProducts10`, `AeolusL0ProductsB16`, `AeolusAdditionalProducts` | 2018-08-22 → 2023-07-28 |
| Biomass | `BiomassLevel0` … `BiomassLevel2bIOC`, `BiomassAux`, `BiomassAuxIOC`, `BiomassAuxRest`, `BiomassCalVal10`, `BiomassSimulated` (17) | 2010-01-01 → 2045-12-31 |
| FLEX | `FLEXL0…Internal` … `FLEXL1AuxCCDBInternal`, `FLEXTestAuxProducts`, `FLEXTestL1Products`, `FLEXTestL2Products`, `FLEXTestRAWL0Products` (17) | 2016-08-01 → 2045-12-31 |

---

## Formats

`--format` (on `search`, `get`, `sync`) takes:

- `zip` - the whole product as one archive;
- `all` - every file of the product;
- a file extension: `h5`, `hdr`, `dbl`, `eef`, `nc`, `bufr`, `tiff`, `xml`, `xsd`, `png`,
  `kml`, `dat`, `eof`, … (a leading dot is accepted: `.h5`).

An explicit `--format` is **strict**: products without that format are skipped with a
warning; no other file is substituted. Without `--format`, each product gets the first
format it has from its mission's priority list:

| Mission | Default (no `--format`) |
|---------|-------------------------|
| EarthCARE | `h5` → `eof` → `dbl` (L1/L2 get `h5`, orbit and AUX files `eof`, L0 `dbl`) |
| Aeolus | `dbl` → `nc` → `bufr` → `eef` |
| Biomass | `zip` |
| FLEX | `zip` |

`default_format` in `[missions.<Name>]` replaces the list with one format.

> **Formats and the registry:** the registry does not separate files by format. Running
> `--registry-save` or `sync` with different `--format` values for the same
> collection/product/baseline mixes both formats in the same registry files. Use one
> `--format` per collection/product/baseline, or a separate `--data-dir` per format.

---

## Filters

Each mission has a closed list of filters; any other is rejected with the list of
available ones (exit 4). `maap search --help` shows what each option means per mission,
e.g. `--frame FRAME[,FRAME...]  EarthCARE: frame letter(s) A-H; Biomass: frame number(s)`.

| Mission | Filters |
|---------|---------|
| EarthCARE | `--orbit NNNNN[X]` (optionally with the frame letter, e.g. `01525E`), `--frame A-H` (comma list) |
| Aeolus | `--orbit` |
| Biomass | `--orbit` (search only), `--track`, `--frame` (numbers), `--repeat-cycle`, `--major-cycle` (comma lists; zero padding accepted, e.g. `--track 038`) |
| FLEX | `--orbit` (search only, absolute orbit) |

`search`, `get` and `sync` send the filters to MAAP. `download --registry` applies them
offline to the registered file names:

- `--orbit` is rejected for Biomass and FLEX (their names carry no absolute orbit), and
  for Aeolus when the registry holds products whose names carry no orbit (e.g. `ALD_U_N_2B`).
- Biomass `--track`/`--frame`/`--repeat-cycle`/`--major-cycle` work offline only for the
  documented types (L1a, L1b, L1c, L2a).

```bash
# EarthCARE: one orbit/frame, a whole orbit, or frames over a period
maap search EarthCAREL1Validated_MAAP CPR_NOM_1B DA --orbit 08962F
maap search EarthCAREL1Validated_MAAP CPR_NOM_1B DA --orbit 08962 --frame C,D
maap search EarthCAREL1Validated_MAAP CPR_NOM_1B DA --start 2024-12-01 --end 2024-12-08 --frame A

# Biomass: track and frame numbers
maap search BiomassLevel1b S1_DGM__1S --date 2025-12-11 --track 38 --frame 249,250

# Aeolus: one day of L1B
maap search AeolusBaseline16Products10 ALD_U_N_1B --date 2023-04-30
```

---

## On-disk layout

### Data

Files mirror the archive, dated by the **sensing time** (first timestamp of the product name):

```
data/{mission}/{collection}/{product}/{baseline}/YYYY/MM/DD/<file>
```

```
data/EarthCARE/EarthCAREL2Validated_MAAP/CPR_CLD_2A/BC/2024/12/01/
  ECA_EXBC_CPR_CLD_2A_20241201T123456Z_20241201T135958Z_07282E.h5
```

A `zip` is saved as `<PRODUCT>.zip` in the day folder:

```
data/Biomass/BiomassLevel1b/S1_DGM__1S/01/2025/12/11/
  BIO_S1_DGM__1S_20251211T135700_20251211T135720_T_G01_M01_C07_T038_F249_01_DO9ZT3.zip
```

With `--product-dir`, files go in `<day>/<PRODUCT>/`, reproducing the product's internal
sub-folders (`<PRODUCT>/<PRODUCT>.zip` for a zip):

```
data/EarthCARE/.../BC/2024/12/01/ECA_EXBC_CPR_CLD_2A_20241201T123456Z_20241201T135958Z_07282E/
  ECA_EXBC_CPR_CLD_2A_20241201T123456Z_20241201T135958Z_07282E.h5
  ECA_EXBC_CPR_CLD_2A_20241201T123456Z_20241201T135958Z_07282E.hdr

data/Biomass/.../01/2025/12/11/BIO_S1_DGM__1S_..._F249_01_DO9ZT3/
  measurement/bio_s1_dgm__1s_..._i_abs.tiff
  annotation/...
```

- **Biomass individual files** (any `--format` other than `zip`) **require `--product-dir`**:
  their names repeat across and within products. The command is rejected before any request.
  The exception is `MPL_ORBPRE`: a single-file product, it downloads without `--product-dir`.
- Aeolus `ALDUN1A_NC` also requires `--product-dir` (or `--out-dir`): its data file
  `L1A_<start>__<stop>.nc` is not named after the product.
- Aeolus `.QR.EEF` files go in `<PRODUCT>/` with `--product-dir`.
- `--out-dir DIR` downloads to `DIR` instead of the structured layout.
- **Products without baseline** go in a `NO_BASELINE` baseline folder (data and registry):
  Biomass `MPL_ORBPRE`; the Aeolus aux types without catalogue version (archive folder
  `NNAA`): `AUX_CHAR__`, `AUX_CLM_L2`, `AUX_LUT_BL`, `AUX_MET_12`, the ten `AUX_PAR_*`,
  `AUX_TEL_12`, `GRND_TRACK`, `MPL_ORBPRE`, `MPL_ORBRES`, `MPL_ORBSCT`, `TLMX__VC1_`; and the
  FLEX aux types `AUX_CCCRAD`, `AUX_DVAERR`, `AUX_FLOLUT`, `AUX_GPRMOD`, `AUX_MACV2_`,
  `AUX_OCONVI`, `AUX_OCONV_`, `AUX_OLISRF`, `AUX_OPAR__`, `AUX_OWV___`, `AUX_REFCEN`,
  `AUX_SIFCOV`, `AUX_SLISRF`, `AUX_SNCONV`, `AUX_SOCONV`, `AUX_UTMTIL`, `AUX_V_TEMP`. Give
  `NO_BASELINE` (any case) as the baseline to search them alone; `sync` without a baseline
  includes them. Any other product whose baseline cannot be read is an error (exit 4,
  "cannot read the baseline of ...") before anything is written.

```bash
maap search BiomassAux MPL_ORBPRE NO_BASELINE --days-back 3
```

### Registry

The registry tracks a download workflow with text files partitioned by sensing date:

```
registry/
├── urls/{mission}/{collection}/{product}/{baseline}/{year}/
│   └── url_YYYYMMDD.txt      # URL|LOCAL_PATH (one per line)
├── downloads/{mission}/{collection}/{product}/{baseline}/{year}/
│   └── dwl_YYYYMMDD.txt      # URL|LOCAL_PATH (one per line)
├── marked/{mission}/{collection}/{product}/{baseline}/{year}/
│   └── mrk_YYYYMMDD.txt      # PATH only (one per line)
└── downloads/.../errors.txt  # URL|ERROR for failed downloads
```

Each file is **discovered** (`search --registry-save`, `sync`), **downloaded**
(`download --registry`, `sync`) and **marked** (`state mark`, by your pipeline);
`state pending` lists what is discovered but not downloaded, or downloaded but not
marked, and `state cleanup` deletes marked files.

### Time filtering

MAAP returns products whose validity period overlaps the requested range. The client
keeps only those whose **sensing time** falls inside the range, so each product belongs
to exactly one day. A product sensed at 23:50 on 31 December is excluded from a
1 January search, even if its validity overlaps it.

```
ECA_JXDA_CPR_NOM_1B_20241201T123456Z_20241201T135958Z_07282E.h5
                    ^^^^^^^^^^^^^^^^ sensing time
```

### Catalogs

- **Queryables** (`catalogs/`): products and baselines of each collection, so `maap list`
  works offline. Downloaded on first use; refresh with `maap catalog update`. It keeps
  going when one collection fails, reports the failures and exits 3.
- **Built catalogs** (`built_catalogs/`): time ranges, orbit ranges and file counts per
  baseline, built with `maap catalog build`; used by `--use-catalog`. Building is
  resumable: progress is saved after every baseline, a failing baseline is skipped and
  reported (exit 3), and re-running fills only the gaps. `--force` rebuilds from scratch
  (only needed after files are deleted from the server).

---

## Mission notes

### EarthCARE

- Names: `ECA_<agency><baseline>_<type>_<sensing start>_<creation>_<orbit><frame>`.
  Source: [EarthCARE Data Handbook, Product Definition and Format](https://earthcarehandbook.earth.esa.int/article/product).
- X-JSG / X-MET products are not indexed by orbit in MAAP, so `--orbit` searches return
  nothing for them. Use frame + time (frames are indexed), or the registry, whose offline
  `--orbit` matches file names:

```bash
maap get EarthCAREL0L1Products_MAAP AUX_JSG_1D --date 2024-09-03 --frame E --out-dir ./
maap search EarthCAREXMETL1DProducts10_MAAP AUX_MET_1D --date 2024-09-03 --registry-save
maap download EarthCAREXMETL1DProducts10_MAAP AUX_MET_1D --registry --orbit 01524E
```

```bash
maap get EarthCAREL1Validated_MAAP ATL_NOM_1B --orbit 01525E          # one orbit and frame
maap sync EarthCAREL2Validated_MAAP CPR_CLD_2A --days-back 3 --frame C,D
```

### Aeolus

- Naming is not publicly documented; only type, sensing start, orbit (when present) and
  baseline are read.
- Unlike older versions, `--registry-save` now registers a day whose search returns as
  many URLs as the day already holds but different ones (e.g. another format); older
  versions skipped such a day.

- The mission ended on 2023-07-28: a range after that (e.g. `--days-back 3`) is rejected
  (exit 4).
- `ALDUN1A_NC` needs `--product-dir` (or `--out-dir`): its data file `L1A_<start>__<stop>.nc`
  is not named after the product.
- Aux types without catalogue version (archive folder `NNAA`) use the baseline `NO_BASELINE`.

```bash
maap get AeolusBaseline16Products10 ALD_U_N_1B --date 2023-04-30            # .DBL files
maap get AeolusBaseline16Products10 ALD_U_N_1B --date 2023-04-30 --format all --product-dir
maap get AeolusBaseline16Products10 ALDUN1A_NC --orbit 27146 --product-dir  # one orbit, netCDF
maap get AeolusAdditionalProducts AUX_PAR_1B NO_BASELINE --date 2023-05-17
```

### Biomass

- Names: `BIO_<type>_<start>_<stop>_<phase>_G<cc>_M<major cycle>_C<repeat cycle>_T<track>_F<frame>_<baseline>_<creation>`.
  Source: [Biomass documentation](https://earth.esa.int/eogateway/missions/biomass/documentation).
- Default download is the whole product as `zip`. For individual files, add `--product-dir`:

```bash
maap get BiomassLevel1b S1_DGM__1S 01 --date 2025-12-11 --track 38
maap get BiomassLevel1b S1_DGM__1S 01 --date 2025-12-11 --track 38 --frame 249 --format tiff --product-dir
maap sync BiomassLevel1b S1_DGM__1S --days-back 7 --repeat-cycle 7
maap get BiomassAux MPL_ORBPRE NO_BASELINE --days-back 7 --format eof   # single file, no --product-dir
```

### FLEX

- Names (L1C and L2): `FLX_<type>_<start>_<stop>_<creation>_…_<baseline>`.
  Source: [FLEX L1C & L2 IPF Product Format Definition](https://earth.esa.int/eogateway/documents/d/earth-online/flex-level-1c-and-level-2-ipf-product-format-definition).
- **Download access must be requested from ESA.** Without it MAAP answers 403 (the error
  message mentions possible missing download access); search and the registry work.

```bash
maap search FLEXL1BEOProductsInternal L1B_OBS___ --date 2026-10-26 --registry-save
maap search FLEXTestAuxProducts AUX_CCCRAD NO_BASELINE --date 2019-01-01
maap list FLEXL1BEOProductsInternal
```

---

## Not supported yet

- **Biomass L2b** (`FP_FH__L2B`, `FP_FD__L2B`, `FP_AGB_L2B`; collections `BiomassLevel2b`,
  `BiomassLevel2bIOC`, empty today): the names carry no time, so time searches skip them
  and downloads reject them ("no sensing time").
- **FLEX downloads are not validated**: search, registry and name parsing are tested, but
  downloads return 403 until ESA grants access.
- **`BiomassAuxRest`**: restricted download access (403 with standard accounts).
- For product types without public naming documentation (Aeolus; EarthCARE X-MET, AUX,
  orbit and L0; Biomass L0, CalVal, Simulated and other AUX; FLEX L0, L1B, RAW, ANC, RAC,
  AUX) only type, sensing start and baseline are read from the name.

---

## Command examples

Global options go before the sub-command: `-v`/`-vv` (verbosity), `--quiet`,
`-c FILE` (config), `-d DIR` (data directory), `--mission NAME`.
Use `maap <command> -h` for the full option list.

### Help and configuration

```bash
maap -h
maap --version
maap config
maap token --days-left
```

### Catalog management

```bash
# Update queryables (all collections of the mission in use, or one)
maap -v catalog update
maap -v catalog update EarthCAREL0L1Products_MAAP
maap -v catalog update EarthCAREL0L1Products_MAAP -o ./my_catalogs

# Build metadata catalogs
maap -v catalog build
maap -v catalog build EarthCAREL0L1Products_MAAP
maap -v catalog build EarthCAREL0L1Products_MAAP CPR_NOM_1B
maap -v catalog build EarthCAREL0L1Products_MAAP CPR_NOM_1B DA
maap -v catalog build EarthCAREL0L1Products_MAAP CPR_NOM_1B --latest-baseline
maap -v catalog build EarthCAREL0L1Products_MAAP CPR_NOM_1B -o ./my_built_catalogs
```

### List (browse)

```bash
maap -v list                                                # collections
maap -v list EarthCAREL0L1Products_MAAP                     # products
maap -v list EarthCAREL0L1Products_MAAP --verify            # refreshed from the API
maap -v list EarthCAREL0L1Products_MAAP CPR_NOM_1B          # baselines
maap -v list EarthCAREL0L1Products_MAAP CPR_NOM_1B --latest-baseline
maap -v list EarthCAREL0L1Products_MAAP CPR_NOM_1B DA       # time range, count
```

### Search

Time options (`--date`, `--start/--end`, `--days-back`) and `--orbit` are mutually
exclusive; `--frame` and the Biomass filters combine with any of them.

```bash
# All baselines, mission start to now
maap -v search EarthCAREL0L1Products_MAAP CPR_NOM_1B

# One day (00:00:00Z-23:59:59Z), or an exact datetime (1 minute buffer)
maap -v search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01
maap -v search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01T12:30:00Z

# Ranges and look-back
maap -v search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --start 2025-01-01 --end 2025-01-07
maap -v search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --start 2025-01-01T00:00:00Z --end 2025-01-01T06:00:00Z
maap -v search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --days-back 7

# Save to a flat URL file, or to the registry (by sensing date)
maap -v search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01 -o urls.txt
maap -v search EarthCAREL0L1Products_MAAP CPR_NOM_1B --start 2025-01-01 --end 2025-01-07 --registry-save

# Frames, format, limits, newest first, built catalog bounds
maap -v search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01 --frame C,D
maap -v search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01 --format hdr
maap -v search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01 --max-items 100
maap -v search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --days-back 3 --newest-first
maap -v search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --use-catalog
```

### Download

One source is required: `--url`, `--url-file` or `--registry`. Time and filter options
apply only with `--registry` and match file names (no MAAP query).

```bash
maap -v download EarthCAREL0L1Products_MAAP CPR_NOM_1B --url "https://catalog.maap.eo.esa.int/data/.../file.h5"
maap -v download EarthCAREL0L1Products_MAAP CPR_NOM_1B --url "https://..." -o ./downloads
maap -v download EarthCAREL0L1Products_MAAP CPR_NOM_1B --url-file urls.txt

maap -v download EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --registry
maap -v download EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --registry --date 2025-01-01
maap -v download EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --registry --start 2025-01-01 --end 2025-01-07
maap -v download EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --registry --frame C,D
maap -v download EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --registry --date 2025-01-01 --dry-run
maap -v download EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --registry --max-items 10
maap -v download BiomassLevel1b S1_DGM__1S 01 --registry --track 38 --product-dir
```

### Get (search + download)

```bash
maap -v get EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01
maap -v get EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --start 2025-01-01 --end 2025-01-03
maap -v get EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01 -o ./flat_downloads
maap -v get EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01 --frame C,D
maap -v get EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01 --product-dir --format all
maap -v get EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01 --dry-run
maap -v get EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01 --max-items 5
```

### Sync (cron)

`sync` searches, registers and downloads day by day (default: last 3 days).

```bash
maap -v sync EarthCAREL0L1Products_MAAP CPR_NOM_1B DA
maap -v sync EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --days-back 7
maap -v sync EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01
maap -v sync EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --start 2025-01-01 --end 2025-01-07
maap -v sync EarthCAREL0L1Products_MAAP CPR_NOM_1B --days-back 3            # all baselines
maap -v sync EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --days-back 3 --frame C,D
maap -v sync EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --days-back 1 -o ./sync_data
maap -v sync EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --days-back 7 --max-items 100
```

### State management

```bash
maap -v state show EarthCAREL0L1Products_MAAP CPR_NOM_1B DA
maap -v state show EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01
maap -v state show EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --start 2025-01-01 --end 2025-01-07

maap -v state pending EarthCAREL0L1Products_MAAP CPR_NOM_1B DA                 # pending downloads
maap -v state pending EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01
maap -v state pending EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --type marks    # downloaded, not marked

maap -v state mark /path/to/file1.h5 /path/to/file2.h5
maap -v state mark -f processed_files.txt

maap -v state cleanup EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --dry-run
maap -v state cleanup EarthCAREL0L1Products_MAAP CPR_NOM_1B DA
```

---

## Common workflows

### Initial data discovery

```bash
maap -v catalog update EarthCAREL0L1Products_MAAP
maap -v list EarthCAREL0L1Products_MAAP
maap -v list EarthCAREL0L1Products_MAAP CPR_NOM_1B
maap -v catalog build EarthCAREL0L1Products_MAAP CPR_NOM_1B DA
maap -v list EarthCAREL0L1Products_MAAP CPR_NOM_1B DA
```

### Search and download

```bash
maap -v search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01 --registry-save
maap -v download EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --registry --date 2025-01-01
maap -v state show EarthCAREL0L1Products_MAAP CPR_NOM_1B DA
```

### Crontab sync

```bash
# m h dom mon dow  command
0 6 * * * maap sync EarthCAREL2Validated_MAAP CPR_CLD_2A DA >> /var/log/maap-sync.log 2>&1
0 7 * * * maap sync BiomassLevel1b S1_DGM__1S --days-back 3 >> /var/log/maap-sync.log 2>&1
```

### Backfill historical data

```bash
maap -v search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --start 2024-06-01 --end 2024-12-31 --registry-save
maap -v download EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --registry --start 2024-06-01 --end 2024-06-30
maap -v download EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --registry --start 2024-07-01 --end 2024-07-31
# ... continue for each month
maap -v state show EarthCAREL0L1Products_MAAP CPR_NOM_1B DA
```

### Processing pipeline

```bash
maap -v sync EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --days-back 1
maap -v state pending EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --type marks > to_process.txt
# ... process the files, then:
maap -v state mark -f processed_files.txt
maap -v state cleanup EarthCAREL0L1Products_MAAP CPR_NOM_1B DA
```

---

## Reliability

Every command is built to be re-run. Transient failures are retried in-process where that
is cheap and safe; whatever survives is skipped, recorded and reported, so a later run
picks up exactly the gaps.

| Operation | In-process retries | On failure |
|-----------|--------------------|------------|
| STAC search (`search`, `sync`, `get`) | 5 transport retries with exponential backoff, each logged; then a second pass at the end of the range retrying every failed day once | Day skipped and recorded → `FAILED DAY:` on stderr, exit 3 |
| Catalog build | The same transport retries; no second pass | Baseline skipped and reported at the end, exit 3 |
| Download | None — one attempt per file, plus one token refresh on 401/403 | File recorded in `errors.txt`, exit 3 |

The retried statuses are **429, 500, 502, 503 and 504**. Anything else (400, 404, a
malformed response) fails immediately. Backoff sleeps 0, 4, 8, 16 and 32 seconds.

A 403 on download can also mean the account has no download access to the collection
(FLEX, `BiomassAuxRest`); the error says so, and the exit code stays 3.

The client never sleeps waiting for a server to recover: it exits 3 and lets the caller
decide when to retry. Re-running is cheap: URLs are registered day by day as found,
existing files are skipped, and downloads are written to a `.part` file renamed into
place only when complete.

---

## Exit codes and wrapper scripts

| Code | Meaning | Wrapper action |
|------|---------|----------------|
| 0 | Success | Nothing to do |
| 2 | Auth fatal | Stop everything; fix credentials/token |
| 3 | Transient | Re-run the same command later; completed work is kept and gaps fill in |
| 4 | Non-transient | Do not retry; fix the request or configuration |

A partially successful run exits 3 and lists each gap on stderr:

    FAILED DAY: 2025-03-14 (503 Server Error ...)
    WARNING: 1 day(s) failed; re-run the same command to fill the gaps

`sync` prefixes the baseline: `FAILED DAY: AC 2025-03-14 (...)`.

Exit 4 covers invalid requests: a filter the mission does not have, an invalid `--frame`
value (e.g. `--frame 12` for EarthCARE), Biomass files without `--product-dir`, a URL
whose baseline cannot be read (`cannot read the baseline of ...`), a configuration error,
or a run whose only failures are file names that cannot be parsed into a data path.

> argparse usage errors (unknown flags, missing arguments) exit 2 by Python convention,
> like auth-fatal; "stop and let a human look" fits both.

```bash
for attempt in 1 2 3; do
  maap sync "$COLLECTION" "$PRODUCT" "$BASELINE" --start "$START" --end "$END"
  rc=$?
  case $rc in
    0) break ;;                                  # complete
    2) echo "auth dead, aborting" >&2; exit 2 ;; # do not retry
    3) sleep $((attempt * 300)) ;;               # transient/partial: re-run fills the gaps
    4) echo "bad request" >&2; exit 4 ;;         # fix the invocation
  esac
done
exit $rc  # 0 if it broke out clean, otherwise the last transient exit code
```

---

## Python API

The library works on the mission of its configuration: `MaapConfig.load()` uses
`default_mission` (EarthCARE by default); pass `mission=` for another one.

```python
from datetime import datetime, timezone
from pathlib import Path

from maap_client import MaapClient, MaapConfig

client = MaapClient()                       # EarthCARE unless configured otherwise

# Browse
collections = client.list_collections()
products = client.list_products("EarthCAREL1Validated_MAAP")
baselines = client.list_baselines("EarthCAREL1Validated_MAAP", "CPR_NOM_1B", verify=True)

# Search (returns SearchResult)
result = client.search(
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
    baseline="BA",
    start=datetime(2024, 12, 1, tzinfo=timezone.utc),
    end=datetime(2024, 12, 31, tzinfo=timezone.utc),
)
print(result.total_count, result.baselines_found)

# Orbit, frames (a mission filter), format
result = client.search("EarthCAREL2Validated_MAAP", "CPR_CLD_2A", orbit="08962F")
result = client.search("EarthCAREL2Validated_MAAP", "CPR_CLD_2A", orbit="8962", filters={"frame": ["C", "D"]})
result = client.search("EarthCAREL2Validated_MAAP", "CPR_CLD_2A", start=datetime(2024, 12, 1, tzinfo=timezone.utc), format="hdr")

# Download (returns DownloadResult)
downloaded = client.download(urls=result.urls, collection="EarthCAREL2Validated_MAAP")
print(len(downloaded.downloaded), len(downloaded.skipped), downloaded.errors)
client.download(urls=result.urls, collection="EarthCAREL2Validated_MAAP", out_dir=Path("./downloads"))

# Search + download, and incremental sync (returns SyncResult)
client.get("EarthCAREL2Validated_MAAP", "CPR_CLD_2A", "BC", start=datetime(2024, 12, 1, tzinfo=timezone.utc))
sync = client.sync("EarthCAREL2Validated_MAAP", "CPR_CLD_2A", "BC")
print(sync.urls_found, sync.urls_downloaded, sync.errors)

# Another mission: mission filters go in `filters`
biomass = MaapClient(MaapConfig.load(mission="Biomass"))
result = biomass.get(
    "BiomassLevel1b", "S1_DGM__1S", "01",
    start=datetime(2025, 12, 11, tzinfo=timezone.utc),
    end=datetime(2025, 12, 11, 23, 59, 59, tzinfo=timezone.utc),
    filters={"track": ["38"], "frame": ["249"]},
)
```

Product names, without network: `parse_product` picks the mission from the name prefix
and returns its typed name (`EarthCAREName`, `AeolusName`, `BiomassName`, `FlexName`),
or `None` for an unknown prefix. Each mission module also has one `extract_<field>` per
field. Pass the whole URL when you have it: some fields (the Aeolus baseline, every
Biomass field) are only in the archive path.

```python
from maap_client.missions import BiomassName, parse_product
from maap_client.missions import aeolus

name = parse_product("ECA_EXBE_ATL_AER_2A_20261027T165657Z_20261027T173059Z_13720B.h5")
print(name.product_type, name.baseline, name.orbit, name.frame)  # ATL_AER_2A BE 13720 B

url = (
    "https://catalog.maap.eo.esa.int/data/biomass-pdgs-01/BiomassLevel1a/2026/03/03/"
    "BIO_S1_SCS__1M_20260303T002946_20260303T003002_T_G01_M02_C07_T001_F062_01_DNOUR5/"
    "BIO_S1_SCS__1M_20260303T002946_20260303T003002_T_G01_M02_C07_T001_F062_01_DNOUR5/"
    "schema/bio-common-types.xsd"
)
bio = parse_product(url)
assert isinstance(bio, BiomassName)
print(bio.track, bio.frame, bio.repeat_cycle, bio.major_cycle)  # 1 62 7 2

print(aeolus.extract_orbit("AE_OPER_ALD_U_N_1B_20230430T223357019_005160010_027148_0002.DBL"))  # 27148

orbit_file = (
    "https://catalog.maap.eo.esa.int/data/biomass-pdgs-01/BiomassAux/2026/10/27/"
    "BIO_OPER_MPL_ORBPRE_20261027T000000_20261110T000000_0001/"
    "BIO_OPER_MPL_ORBPRE_20261027T000000_20261110T000000_0001/"
    "BIO_OPER_MPL_ORBPRE_20261027T000000_20261110T000000_0001.EOF"
)
print(parse_product(orbit_file).baseline)  # NO_BASELINE
```

Day-by-day search for large ranges (days that keep failing are recorded in
`client.searcher.last_failed_days` as `(date, error)` tuples):

```python
for day_urls in client.searcher.search_urls_iter_day(
    collection="EarthCAREL1Validated_MAAP",
    product_type="CPR_NOM_1B",
    baseline="DA",
    start=datetime(2024, 6, 1, tzinfo=timezone.utc),
    end=datetime(2024, 12, 31, tzinfo=timezone.utc),
):
    print(len(day_urls))
```

State tracking:

```python
tracker = client.get_tracker("EarthCAREL2Validated_MAAP", "CPR_CLD_2A", "BC")
pending = tracker.get_pending_downloads()
pending_marks = tracker.get_pending_mark_paths()
tracker.mark("/path/to/file.h5")
```

---

## Troubleshooting

**Token expired** — `AuthenticationError: Failed to refresh token: 401 Unauthorized`:
get a new token from https://portal.maap.eo.esa.int/ini/services/auth/token/90dToken.php
(`maap token` shows the expiry).

**Credentials not found** — `CredentialsError: Credentials file not found`: create
`~/.maap/credentials.txt`.

**403 Forbidden on download** — the account may have no download access to that
collection (FLEX, `BiomassAuxRest`); request it from ESA.

**No data found** — check baselines with `maap list <collection> <product>`, the date
range, and `maap mission show` for the mission's dates.

**"… has no --track; available filters: …"** — the filter does not exist for the
collection's mission; see [Filters](#filters).

**Timezone error** — `InvalidRequestError: 'start' must be timezone-aware`: use
`datetime(2024, 12, 1, tzinfo=timezone.utc)` in Python.

**Catalog not found** — `FileNotFoundError: Built catalog not found for ...`: run
`maap catalog build <collection>`.
