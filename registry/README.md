# Registry

The text files that track download workflows (found URLs, completed downloads and
marked files) are stored in `registry_dir` from the configuration file
(default: `~/.maap/registry`, see `maap config`), not in this folder. Its contents
are ignored by git.

Layout:

```
{registry_dir}/urls/{mission}/{collection}/{product}/{baseline}/{yyyy}/url_YYYYMMDD.txt
{registry_dir}/downloads/{mission}/{collection}/{product}/{baseline}/{yyyy}/dwl_YYYYMMDD.txt
{registry_dir}/marked/{mission}/{collection}/{product}/{baseline}/{yyyy}/mrk_YYYYMMDD.txt
```
