"""CLI command handlers for MAAP client."""

import argparse
import sys
from pathlib import Path

from maap_client import MaapClient, MaapConfig, InvalidRequestError
from maap_client.cli_helpers import (
    get_client,
    resolve_date_args,
    validate_time_args,
)
from maap_client.utils import to_zulu


# --- Command handlers ---


def cmd_catalog_update(args: argparse.Namespace) -> int:
    """Handle 'catalog update' command."""
    client = get_client(args)

    collections = [args.collection] if args.collection else None
    out_dir = args.out_dir if hasattr(args, 'out_dir') and args.out_dir else None
    results = client.update_catalogs(collections=collections, force=True, out_dir=out_dir)

    for collection, path in results.items():
        print(f"{path}")

    print(f"Updated {len(results)} catalog(s)")

    return 0


def cmd_catalog_build(args: argparse.Namespace) -> int:
    """Handle 'catalog build' command."""
    client = get_client(args)

    # Validate time arguments
    validation_error = validate_time_args(args)
    if validation_error:
        print(f"Error: {validation_error}", file=sys.stderr)
        return 1

    # Resolve time range
    start, end = resolve_date_args(args)

    # Use config's built_catalog_dir if --out-dir not specified
    out_dir = args.out_dir if args.out_dir else None

    try:
        results = client.build_catalog(
            collection=args.collection,
            product_type=args.product,
            baseline=args.baseline,
            latest_baseline=getattr(args, 'latest_baseline', False),
            start=start,
            end=end,
            force=getattr(args, 'force', False),
            out_dir=out_dir,
            verbose=getattr(args, 'verbose', 0) >= 1,
        )

        for collection, path in results.items():
            print(f"Wrote catalog to {path}")

        return 0

    except InvalidRequestError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_list(args: argparse.Namespace) -> int:
    """
    Handle 'list' command with hierarchical behavior.

    0 args: list collections
    1 arg:  list products from queryables
    2 args: list baselines from built catalog
    3 args: show baseline info from built catalog
    """
    from maap_client.exceptions import CatalogError

    client = get_client(args)

    # Level 0: List collections
    if args.collection is None:
        for collection in client.list_collections():
            print(collection)
        return 0

    # Level 1: List products (from queryables)
    if args.product is None:
        try:
            verify = getattr(args, 'verify', False)
            products = client.list_products(args.collection, from_built=False, verify=verify)
            for product in products:
                print(product)
            return 0
        except (FileNotFoundError, CatalogError) as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    # Level 2: List baselines (from queryables)
    if args.baseline is None:
        try:
            verify = getattr(args, 'verify', False)
            baselines = client.list_baselines(args.collection, args.product, from_built=True, verify=verify)
            # If --latest-baseline, sort alphabetically and return only the last one
            if getattr(args, 'latest_baseline', False):
                baselines = sorted(baselines)
                if baselines:
                    print(baselines[-1])
            else:
                for baseline in baselines:
                    print(baseline)
            return 0
        except (FileNotFoundError, ValueError) as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    # Level 3: Show baseline info
    baseline_info = client.get_baseline_info(
        args.collection,
        args.product,
        args.baseline,
        from_built=True,
    )

    if not baseline_info:
        print(
            f"Error: Baseline {args.baseline.upper()} not found in built catalog. "
            f"Run: maap catalog build {args.collection} {args.product} {args.baseline}",
            file=sys.stderr,
        )
        return 1

    # Print info (same format as current 'maap info')
    print(f"Info for {args.collection}/{args.product}/{args.baseline.upper()}:")
    print(f"Time start:          {baseline_info.time_start}")
    print(f"Time end:            {baseline_info.time_end}")
    print(f"Orbit start:         {baseline_info.frame_start or ''}")
    print(f"Orbit end:           {baseline_info.frame_end or ''}")
    print(f"Total:               {baseline_info.count}")
    if hasattr(baseline_info, 'updated_at') and baseline_info.updated_at:
        print(f"Updated:             {baseline_info.updated_at}")

    return 0


def cmd_search(args: argparse.Namespace) -> int:
    """Handle 'search' command (unified: time-based or orbit-based)."""
    client = get_client(args)

    # Validate arguments
    validation_error = validate_time_args(args)
    if validation_error:
        print(f"Error: {validation_error}", file=sys.stderr)
        return 1

    registry_save = getattr(args, 'registry_save', False)
    orbit = getattr(args, 'orbit', None)
    use_catalog = getattr(args, 'use_catalog', False)

    # Resolve time range (for time-based search)
    start, end = resolve_date_args(args) if not orbit else (None, None)

    try:
        # Use facade search() method
        result = client.search(
            collection=args.collection,
            product_type=args.product,
            baseline=args.baseline,
            start=start,
            end=end,
            orbit=orbit,
            use_catalog=use_catalog,
            max_items=args.max_items,
            verbose=getattr(args, 'verbose', 0) >= 1,
        )
        urls = result.urls

    except InvalidRequestError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Save to registry if requested
    if registry_save and urls:
        new_count, files_written = client.save_to_registry(
            urls=urls,
            collection=args.collection,
            product_type=args.product,
        )
        num_files = len(files_written)
        if new_count > 0:
            if num_files == 1:
                print(f"Saved {new_count} new URLs to {files_written[0]} ({len(urls)} total)", file=sys.stderr)
            else:
                print(f"Saved {new_count} new URLs to {num_files} registry files ({len(urls)} total)", file=sys.stderr)
        else:
            print(f"No new URLs ({len(urls)} already exist in registry)", file=sys.stderr)

    # Handle output
    if args.url_file:
        with open(args.url_file, "w") as f:
            for url in urls:
                f.write(url + "\n")
        print(f"Wrote {len(urls)} URLs to {args.url_file}")
    elif not registry_save:
        # Print to stdout if not saved to registry
        for url in urls:
            print(url)

    return 0


def cmd_download(args: argparse.Namespace) -> int:
    """Handle 'download' command."""
    client = get_client(args)

    # Validate time arguments (only when using --registry with time filters)
    if args.registry:
        validation_error = validate_time_args(args)
        if validation_error:
            print(f"Error: {validation_error}", file=sys.stderr)
            return 1

    try:
        # Download from registry
        if args.registry:
            start, end = resolve_date_args(args)
            if start or end:
                start, end = client.normalize_time_range(start, end)

            result = client.download_from_registry(
                collection=args.collection,
                product_type=args.product,
                baseline=args.baseline,
                start=start,
                end=end,
                out_dir=args.out_dir,
                dry_run=args.dry_run,
                verbose=getattr(args, 'verbose', 0) >= 1,
            )

        # Download from single URL
        elif args.url:
            result = client.download(
                urls=[args.url],
                collection=args.collection,
                out_dir=args.out_dir,
                dry_run=args.dry_run,
                verbose=getattr(args, 'verbose', 0) >= 1,
            )

        # Download from URL file
        elif args.url_file:
            from maap_client.registry import read_pairs_file
            url_records = read_pairs_file(args.url_file)
            urls = [url for url, _ in url_records]
            result = client.download(
                urls=urls,
                collection=args.collection,
                out_dir=args.out_dir,
                dry_run=args.dry_run,
                verbose=getattr(args, 'verbose', 0) >= 1,
            )

        else:
            print("Error: No URL source specified (--registry, --url, or --url-file)", file=sys.stderr)
            return 1

        # Report results
        if result.errors:
            for error in result.errors:
                print(f"Error: {error}", file=sys.stderr)

        return 1 if result.errors else 0

    except InvalidRequestError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_get(args: argparse.Namespace) -> int:
    """Handle 'get' command (search + download in one step)."""
    client = get_client(args)

    # Validate arguments
    validation_error = validate_time_args(args)
    if validation_error:
        print(f"Error: {validation_error}", file=sys.stderr)
        return 1

    orbit = getattr(args, 'orbit', None)

    try:
        start, end = resolve_date_args(args) if not orbit else (None, None)
        result = client.get(
            collection=args.collection,
            product_type=args.product,
            baseline=args.baseline,
            start=start,
            end=end,
            orbit=orbit,
            out_dir=getattr(args, 'out_dir', None),
            max_items=args.max_items,
            dry_run=getattr(args, 'dry_run', False),
            verbose=getattr(args, 'verbose', 0) >= 1,
        )

        # Report results
        if result.errors:
            for error in result.errors:
                print(f"Error: {error}", file=sys.stderr)

        return 1 if result.errors else 0

    except InvalidRequestError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_sync(args: argparse.Namespace) -> int:
    """Handle 'sync' command (crontab-friendly incremental sync)."""
    # Validate time arguments
    validation_error = validate_time_args(args)
    if validation_error:
        print(f"Error: {validation_error}", file=sys.stderr)
        return 1

    # Handle --out-dir override
    if args.out_dir:
        config = MaapConfig.load(args.config) if args.config else MaapConfig.load()
        config.data_dir = args.out_dir
        client = MaapClient(config)
    else:
        client = get_client(args)

    # Calculate time range
    start, end = resolve_date_args(args)

    try:
        # Use facade sync() method
        result = client.sync(
            collection=args.collection,
            product_type=args.product,
            baseline=args.baseline,
            start=start,
            end=end,
            max_items=args.max_items,
            verbose=getattr(args, 'verbose', 0) >= 1,
        )

        # Report results
        if result.errors:
            for error in result.errors:
                print(f"Error: {error}", file=sys.stderr)
            return 1

        return 0

    except InvalidRequestError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_state_show(args: argparse.Namespace) -> int:
    """Handle 'state show' command."""
    client = get_client(args)
    tracker = client.get_tracker(args.collection, args.product, args.baseline)

    # Resolve --date to start/end if provided
    start, end = resolve_date_args(args)

    stats = tracker.get_stats(start, end)

    header = f"State for {args.collection}/{args.product}/{args.baseline}"
    if start or end:
        start_str = to_zulu(start) if start else "..."
        end_str = to_zulu(end) if end else "..."
        header += f"({start_str} to {end_str})"
    print(f"{header}:")
    print(f"Total URLs:          {stats['total_urls']}")
    print(f"Downloaded:          {stats['downloaded']}")
    print(f"Marked:              {stats['marked']}")
    print(f"Errors:              {stats['errors']}")
    print(f"Pending downloads:   {stats['pending_downloads']}")
    print(f"Pending marks:       {stats['pending_marks']}")

    return 0


def cmd_state_pending(args: argparse.Namespace) -> int:
    """Handle 'state pending' command."""
    client = get_client(args)
    tracker = client.get_tracker(args.collection, args.product, args.baseline)

    # Resolve --date to start/end if provided
    start, end = resolve_date_args(args)

    if args.type == "downloads":
        # Return URLs for downloading
        pending = sorted(tracker.get_pending_downloads(start, end))
        for url in pending:
            print(url)
    else:
        # Return paths for marking/processing
        pending = tracker.get_pending_mark_paths(start, end)
        for path in pending:
            print(path)

    return 0


def cmd_state_mark(args: argparse.Namespace) -> int:
    """Handle 'state mark' command."""
    from pathlib import Path
    from maap_client.paths import extract_info

    client = get_client(args)
    collections = client.config.collections

    # Collect paths to mark
    items = []
    if args.file:
        with open(args.file, "r") as f:
            items = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    if args.paths:
        items.extend(args.paths)

    if not items:
        print("No paths provided", file=sys.stderr)
        return 1

    # Group items by (collection, product, baseline)
    items_by_key: dict[tuple[str, str, str], list[str]] = {}

    for item in items:
        info = extract_info(item)
        if info["product_type"] is None or info["baseline"] is None:
            print(f"Error: cannot parse path: {item}", file=sys.stderr)
            return 1

        # Extract collection from path parts
        collection = None
        for part in Path(item).parts:
            if part in collections:
                collection = part
                break
        if collection is None:
            print(f"Error: cannot extract collection from path: {item}", file=sys.stderr)
            return 1

        key = (collection, info["product_type"], info["baseline"])

        if key not in items_by_key:
            items_by_key[key] = []
        items_by_key[key].append(item)

    # Process each group
    marked = 0
    failed = 0

    for (collection, product, baseline), paths in items_by_key.items():
        tracker = client.get_tracker(collection, product, baseline)

        for path in paths:
            if tracker.mark(path):
                marked += 1
            else:
                print(f"Warning: could not extract date from path: {path}", file=sys.stderr)
                failed += 1

    print(f"Marked {marked} files", file=sys.stderr)
    if failed:
        print(f"Failed: {failed} paths", file=sys.stderr)
    return 0


def cmd_state_cleanup(args: argparse.Namespace) -> int:
    """Handle 'state cleanup' command."""
    client = get_client(args)
    tracker = client.get_tracker(args.collection, args.product, args.baseline)

    deleted = tracker.cleanup_marked(dry_run=args.dry_run)

    if args.dry_run:
        print(f"Would delete {len(deleted)} files:")
        for path in deleted:
            print(f"{path}")
    else:
        print(f"Deleted {len(deleted)} files")

    return 0


def cmd_config(args: argparse.Namespace) -> int:
    """Handle 'config' command - show loaded configuration."""
    config = MaapConfig.load(args.config) if args.config else MaapConfig.load()

    print("Loaded configuration:")
    print(f"data_dir:          {config.data_dir}")
    print(f"catalog_dir:       {config.catalog_dir}")
    print(f"built_catalog_dir: {config.built_catalog_dir}")
    print(f"registry_dir:      {config.registry_dir}")
    print(f"credentials_file:  {config.credentials_file}")
    print(f"catalog_url:       {config.catalog_url}")
    print(f"token_url:         {config.token_url}")
    print(f"mission:           {config.mission}")
    print(f"mission_start:     {config.mission_start}")
    print(f"mission_end:       {config.mission_end}")

    # Show config file location
    config_path = Path("~/.maap/config.toml").expanduser()
    if config_path.exists():
        print(f"\nConfig file: {config_path}")
    else:
        print("\nConfig file: not found (using defaults)")

    return 0
