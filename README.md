# MAAP Client

<p>
  <img src="https://raw.githubusercontent.com/earthfocus/maap_client/master/logos/readme/earthcare.png" alt="EarthCARE" height="120">
  <img src="https://raw.githubusercontent.com/earthfocus/maap_client/master/logos/readme/aeolus.png" alt="Aeolus" height="120">
  <img src="https://raw.githubusercontent.com/earthfocus/maap_client/master/logos/readme/biomass.png" alt="Biomass" height="120">
  <img src="https://raw.githubusercontent.com/earthfocus/maap_client/master/logos/readme/flex.png" alt="FLEX" height="120">
  <img src="https://raw.githubusercontent.com/earthfocus/maap_client/master/logos/readme/cryosat.png" alt="CryoSat" height="120">
</p>

Mission patches © ESA

[![PyPI](https://img.shields.io/pypi/v/maap-client?label=PyPI)](https://pypi.org/project/maap-client/)

A Python client for ESA MAAP satellite data, with a CLI (`maap`) and a Python library.
It browses the MAAP catalogue, searches products by date, orbit or mission-specific
filters, and downloads them with your MAAP credentials into a predictable dated layout,
with text-file tracking for unattended pipelines. It supports EarthCARE, Aeolus, Biomass, FLEX and CryoSat.

| Mission | Default format | Access |
|---------|----------------|--------|
| EarthCARE | `h5` (then `eof`, `dbl`) | MAAP offline token |
| Aeolus | `dbl` (then `nc`, `bufr`, `eef`) | MAAP offline token |
| Biomass | `zip` (whole product) | MAAP offline token; `BiomassAuxRest` is restricted; L2b [not supported yet](EXAMPLES.md#not-supported-yet) |
| FLEX | `zip` (whole product) | Download access must be requested from ESA; downloads [not yet validated](EXAMPLES.md#not-supported-yet) |
| CryoSat | `nc` | MAAP offline token |

The default format applies only when no `--format` is given. See
[what is not supported yet](EXAMPLES.md#not-supported-yet) for current limitations.

---

## Quickstart

### 1. Install

```bash
pip install maap-client
```

### 2. Credentials

1. Go to https://portal.maap.eo.esa.int/ini/services/auth/token/
2. Log in with your ESA account and request a 90-day offline token.
3. Create `~/.maap/credentials.txt`:

```
CLIENT_ID=offline-token
CLIENT_SECRET=p1eL7uonXs6MDxtGbgKdPVRAmnGxHpVE
OFFLINE_TOKEN=<your_token>
```

`maap token` shows when the token expires (`--days-left` prints only the days, for scripts).
Run `maap config` to see the paths and the mission in use.

### 3. How the mission is chosen

Every collection belongs to one mission, so **the collection decides**: a command
given `BiomassLevel1b` works on Biomass whatever else is set. Download URLs decide
it the same way. Only when nothing decides it (e.g. `maap list` or `maap catalog update`
without a collection), the mission comes from, highest first:

1. `--mission <name>` (before or after the sub-command)
2. the `MAAP_MISSION` environment variable
3. `maap mission use <name>` (saved in `~/.maap/active_mission`)
4. `default_mission` in `~/.maap/config.toml`
5. `EarthCARE`

```bash
maap mission list            # known missions, the active one marked
maap mission show Biomass    # collections, dates, default formats, filters
```

### 4. Search and download

```bash
# Find CPR_NOM_1B products of baseline DA sensed on one day and save their URLs
maap search EarthCAREL1Validated_MAAP CPR_NOM_1B DA --date 2024-12-01 --url-file urls.txt

# Download them into data/EarthCARE/EarthCAREL1Validated_MAAP/CPR_NOM_1B/DA/2024/12/01/
maap download EarthCAREL1Validated_MAAP CPR_NOM_1B DA --url-file urls.txt
```

The same for Biomass (whole products as `.zip`, filtered by track):

```bash
maap get BiomassLevel1b S1_DGM__1S 01 --date 2025-12-11 --track 38
```

---

## Main workflows

```bash
# Browse: collections, products, baselines (from the local catalogue)
maap list
maap list EarthCAREL1Validated_MAAP
maap list EarthCAREL1Validated_MAAP CPR_NOM_1B

# One-off: search and download in one step
maap get EarthCAREL1Validated_MAAP CPR_NOM_1B DA --orbit 08962 --frame C,D

# Pipeline: register URLs, then download what is still pending
maap search EarthCAREL1Validated_MAAP CPR_NOM_1B DA --start 2024-12-01 --end 2024-12-07 --registry-save
maap download EarthCAREL1Validated_MAAP CPR_NOM_1B DA --registry

# Scheduled: search + register + download the last 3 days (for cron)
maap sync EarthCAREL2Validated_MAAP CPR_CLD_2A DA

# Tracking: what is pending, mark processed files, free disk space
maap state show EarthCAREL1Validated_MAAP CPR_NOM_1B DA
maap state mark data/EarthCARE/.../file.h5
maap state cleanup EarthCAREL1Validated_MAAP CPR_NOM_1B DA --dry-run
```

Use `maap <command> -h` for every option. Filters depend on the mission
(EarthCARE `--orbit`/`--frame`; Biomass `--track`, `--frame`, `--repeat-cycle`,
`--major-cycle`; Aeolus and FLEX `--orbit`; CryoSat `--orbit`; EarthCARE, Biomass and
CryoSat also `--orbit-direction ascending|descending`, with search only); a filter the
mission does not have is rejected with the list of available ones.

### Automation

Commands given a collection (`list <collection>`, `search`, `download`, `get`, `sync`,
`state show|pending|cleanup`, `catalog update|build <collection>`), `download --url/--url-file`
and `state mark` take the mission from their inputs, so a `maap mission use` typed on the
same machine never changes what they do.

Commands that do **not** determine it (`catalog update` and `catalog build` without a
collection, `list` without a collection, `config`, `mission show` without a name) follow
the selection order above, including the persisted `maap mission use`. In scripts and cron
jobs, pass `--mission` or set `MAAP_MISSION` for those:

```bash
0 5 * * * MAAP_MISSION=Biomass maap catalog update
0 6 * * * maap sync EarthCAREL2Validated_MAAP CPR_CLD_2A DA
```

Every command exits with a classified status, so wrappers need no log parsing:
`0` success, `2` authentication failed (fix the token), `3` transient or partial
failure (re-run the same command later; done work is kept), `4` invalid request
(fix the command or configuration).

---

## More

[EXAMPLES.md](EXAMPLES.md) covers every command and option, configuration
(`config.toml`, environment variables, per-mission overrides), the on-disk layout
of data and registry, formats and filters per mission, reliability and exit codes,
the Python API, troubleshooting and the limitations of this version.

## Links

- PyPI: https://pypi.org/project/maap-client/
- ESA MAAP Portal: https://portal.maap.eo.esa.int
- MAAP Catalog: https://catalog.maap.eo.esa.int
- Token Request: https://portal.maap.eo.esa.int/ini/services/auth/token/90dToken.php

## Contact

Report issues or comments to info [at] earthfocus [dot] io
