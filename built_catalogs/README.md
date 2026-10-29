# Example built catalogs

These files are examples of the catalogs built by the client
(`{collection}_collection.json`): per product and baseline, the time and frame range
and the product count. They are an EarthCARE-only snapshot from 2026-02-06 and are
not kept up to date.

The client does not read this folder. Built catalogs are stored in
`built_catalog_dir` from the configuration file (default: `~/.maap/built_catalogs`,
see `maap config`). Build them with:

```bash
maap catalog build [collection [product [baseline]]]
```
