# Example catalog queryables

These files are examples of the collection queryables the client downloads from the
MAAP STAC API (`{collection}_queryables.json`). They are an EarthCARE-only snapshot
from 2026-02-06 and are not kept up to date.

The client does not read this folder. Queryables are stored in `catalog_dir` from the
configuration file (default: `~/.maap/catalogs`, see `maap config`). They are
downloaded automatically the first time a collection is used, or refreshed with:

```bash
maap catalog update [collection]
```
