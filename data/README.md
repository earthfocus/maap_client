# Data

Downloaded products are stored in `data_dir` from the configuration file
(default: `~/.maap/data`, see `maap config`), not in this folder. Its contents are
ignored by git.

Layout:

```
{data_dir}/{mission}/{collection}/{product}/{baseline}/{yyyy}/{mm}/{dd}/{file}
```
