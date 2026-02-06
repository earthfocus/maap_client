"""Allow running as `python -m maap_client`."""

from maap_client.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
