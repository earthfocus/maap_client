"""CLI command handlers for MAAP client."""

import argparse
import os
import sys
from pathlib import Path

from maap_client import MaapClient, MaapConfig, InvalidRequestError
from maap_client.cli_helpers import (
    collect_filter_args,
    get_client,
    load_config,
    mission_client,
    report_failed_days,
    resolve_date_args,
    validate_download_filter_args,
    validate_time_args,
)
from maap_client.exceptions import classify_exit_code, EXIT_NON_TRANSIENT, EXIT_TRANSIENT
from maap_client.filters import option_flag
from maap_client.mission_select import resolve_mission, write_active_mission
from maap_client.missions import MISSIONS, get_mission, mission_for_collection, parse_product
from maap_client.utils import normalize_baseline, to_zulu


# --- Command handlers ---


def cmd_catalog_update(args: argparse.Namespace) -> int:
    """Handle 'catalog update' command."""
    client = get_client(args)

    collections = [args.collection] if args.collection else None
    out_dir = args.out_dir if hasattr(args, 'out_dir') and args.out_dir else None
    failures: list[tuple[str, str]] = []
    results = client.update_catalogs(
        collections=collections, force=True, out_dir=out_dir, failures_out=failures
    )

    for collection, path in results.items():
        print(f"{path}")

    print(f"Updated {len(results)} catalog(s)")

    if failures:
        print(f"{len(failures)} collection(s) failed:", file=sys.stderr)
        for coll, err in failures:
            print(f"  {coll}: {err}", file=sys.stderr)
        print("Re-run the same command to retry the failed collections.", file=sys.stderr)
        return EXIT_TRANSIENT

    return 0


def cmd_catalog_build(args: argparse.Namespace) -> int:
    """Handle 'catalog build' command."""
    client = get_client(args)

    # Use config's built_catalog_dir if --out-dir not specified
    out_dir = args.out_dir if args.out_dir else None

    try:
        failures: list[tuple[str, str, str, str]] = []
        results = client.build_catalog(
            collection=args.collection,
            product_type=args.product,
            baseline=args.baseline,
            latest_baseline=getattr(args, 'latest_baseline', False),
            force=getattr(args, 'force', False),
            out_dir=out_dir,
            verbose=getattr(args, 'verbose', 0) >= 1,
            failures_out=failures,
        )

        for collection, path in results.items():
            print(f"Wrote catalog to {path}")

        if failures:
            print(f"{len(failures)} baseline(s) failed after retries:", file=sys.stderr)
            for coll, prod, baseline, err in failures:
                print(f"  {coll}/{prod}/{baseline}: {err}", file=sys.stderr)
            print(
                "Re-run the same command to fill only the gaps "
                "(if a baseline was deleted on the server, use --force).",
                file=sys.stderr,
            )
            return EXIT_TRANSIENT

        return 0

    except InvalidRequestError as e:
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_NON_TRANSIENT
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return classify_exit_code(e)


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
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            return EXIT_NON_TRANSIENT
        except CatalogError as e:
            print(f"Error: {e}", file=sys.stderr)
            return classify_exit_code(e)

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
            return EXIT_NON_TRANSIENT

    # Level 3: Show baseline info
    baseline_info = client.get_baseline_info(
        args.collection,
        args.product,
        normalize_baseline(args.baseline),
        from_built=True,
    )

    if not baseline_info:
        print(
            f"Error: Baseline {args.baseline.upper()} not found in built catalog. "
            f"Run: maap catalog build {args.collection} {args.product} {args.baseline}",
            file=sys.stderr,
        )
        return EXIT_NON_TRANSIENT

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
    filters = collect_filter_args(args)

    # Validate arguments
    validation_error = validate_time_args(args)
    if validation_error:
        print(f"Error: {validation_error}", file=sys.stderr)
        return EXIT_NON_TRANSIENT

    registry_save = getattr(args, 'registry_save', False)
    orbit = getattr(args, 'orbit', None)
    use_catalog = getattr(args, 'use_catalog', False)

    # Resolve time range (for time-based search)
    start, end = resolve_date_args(args) if not orbit else (None, None)

    on_day = None
    accumulated_new_count = 0
    accumulated_files: list = []
    if registry_save:
        def on_day(day_urls):
            n, files = client.save_to_registry(
                urls=day_urls,
                collection=args.collection,
                product_type=args.product,
            )
            nonlocal accumulated_new_count, accumulated_files
            accumulated_new_count += n
            accumulated_files.extend(f for f in files if f not in accumulated_files)

    try:
        # Use facade search() method
        result = client.search(
            collection=args.collection,
            product_type=args.product,
            baseline=args.baseline,
            start=start,
            end=end,
            orbit=orbit,
            filters=filters,
            use_catalog=use_catalog,
            max_items=args.max_items,
            verbose=getattr(args, 'verbose', 0) >= 1,
            format=getattr(args, 'format', None),
            reverse=getattr(args, 'newest_first', False),
            on_day=on_day,
        )
        urls = result.urls

    except InvalidRequestError as e:
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_NON_TRANSIENT
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return classify_exit_code(e)

    # Save to registry if requested. When on_day already saved incrementally
    # (long ranges), this final call covers only leftovers from the ≤10-day
    # and orbit paths where on_day never fires; combine both into one summary
    # so the incremental saves aren't hidden behind a stale "no new URLs".
    if registry_save and urls:
        try:
            new_count, files_written = client.save_to_registry(
                urls=urls,
                collection=args.collection,
                product_type=args.product,
            )
        except InvalidRequestError as e:
            print(f"Error: {e}", file=sys.stderr)
            return EXIT_NON_TRANSIENT
        total_new_count = accumulated_new_count + new_count
        total_files = list(accumulated_files)
        total_files.extend(f for f in files_written if f not in total_files)
        num_files = len(total_files)
        if total_new_count > 0:
            if num_files == 1:
                print(f"Saved {total_new_count} new URLs to {total_files[0]} ({len(urls)} total)", file=sys.stderr)
            else:
                print(f"Saved {total_new_count} new URLs to {num_files} registry files ({len(urls)} total)", file=sys.stderr)
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

    report_failed_days(result.failed_days)
    return EXIT_TRANSIENT if result.failed_days else 0


def cmd_download(args: argparse.Namespace) -> int:
    """Handle 'download' command."""
    client = get_client(args)

    filter_error = validate_download_filter_args(args)
    if filter_error:
        print(f"Error: {filter_error}", file=sys.stderr)
        return EXIT_NON_TRANSIENT
    filters = collect_filter_args(args)

    # Validate time arguments (only when using --registry with time filters)
    if args.registry:
        validation_error = validate_time_args(args, orbit_is_filter=True)
        if validation_error:
            print(f"Error: {validation_error}", file=sys.stderr)
            return EXIT_NON_TRANSIENT

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
                orbit=getattr(args, 'orbit', None),
                filters=filters,
                out_dir=args.out_dir,
                dry_run=args.dry_run,
                verbose=getattr(args, 'verbose', 0) >= 1,
                product_dir=getattr(args, 'product_dir', False),
                reverse=getattr(args, 'newest_first', False),
            )

        # Download from single URL
        elif args.url:
            result = client.download(
                urls=[args.url],
                collection=args.collection,
                out_dir=args.out_dir,
                dry_run=args.dry_run,
                verbose=getattr(args, 'verbose', 0) >= 1,
                product_dir=getattr(args, 'product_dir', False),
                reverse=getattr(args, 'newest_first', False),
            )

        # Download from URL file
        elif args.url_file:
            from maap_client.registry import read_pairs_file
            if not args.url_file.exists():
                print(f"Error: URL file not found: {args.url_file}", file=sys.stderr)
                return EXIT_NON_TRANSIENT
            try:
                url_records = read_pairs_file(args.url_file)
            except OSError as e:
                print(f"Error: {e}", file=sys.stderr)
                return EXIT_NON_TRANSIENT
            urls = [url for url, _ in url_records]
            result = client.download(
                urls=urls,
                collection=args.collection,
                out_dir=args.out_dir,
                dry_run=args.dry_run,
                verbose=getattr(args, 'verbose', 0) >= 1,
                product_dir=getattr(args, 'product_dir', False),
                reverse=getattr(args, 'newest_first', False),
            )

        else:
            print("Error: No URL source specified (--registry, --url, or --url-file)", file=sys.stderr)
            return EXIT_NON_TRANSIENT

        # Report results
        for error in result.errors:
            print(f"Error: {error}", file=sys.stderr)
        for error in result.permanent_errors:
            print(f"Error: {error}", file=sys.stderr)

        if result.errors:
            return EXIT_TRANSIENT
        if result.permanent_errors:
            return EXIT_NON_TRANSIENT
        return 0

    except InvalidRequestError as e:
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_NON_TRANSIENT
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return classify_exit_code(e)


def cmd_get(args: argparse.Namespace) -> int:
    """Handle 'get' command (search + download in one step)."""
    client = get_client(args)
    filters = collect_filter_args(args)

    # Validate arguments
    validation_error = validate_time_args(args)
    if validation_error:
        print(f"Error: {validation_error}", file=sys.stderr)
        return EXIT_NON_TRANSIENT

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
            filters=filters,
            out_dir=getattr(args, 'out_dir', None),
            max_items=args.max_items,
            dry_run=getattr(args, 'dry_run', False),
            verbose=getattr(args, 'verbose', 0) >= 1,
            format=getattr(args, 'format', None),
            product_dir=getattr(args, 'product_dir', False),
            reverse=getattr(args, 'newest_first', False),
        )

        # Report results
        for error in result.errors:
            print(f"Error: {error}", file=sys.stderr)
        for error in result.permanent_errors:
            print(f"Error: {error}", file=sys.stderr)

        report_failed_days(result.failed_days)
        if result.errors or result.failed_days:
            return EXIT_TRANSIENT
        if result.permanent_errors:
            return EXIT_NON_TRANSIENT
        return 0
    except InvalidRequestError as e:
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_NON_TRANSIENT
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return classify_exit_code(e)


def cmd_sync(args: argparse.Namespace) -> int:
    """Handle 'sync' command (crontab-friendly incremental sync)."""
    # Validate time arguments
    validation_error = validate_time_args(args)
    if validation_error:
        print(f"Error: {validation_error}", file=sys.stderr)
        return EXIT_NON_TRANSIENT

    client = get_client(args)
    filters = collect_filter_args(args)
    # --out-dir overrides the data directory (and -d/--data-dir)
    if args.out_dir:
        client.config.data_dir = args.out_dir

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
            filters=filters,
            max_items=args.max_items,
            verbose=getattr(args, 'verbose', 0) >= 1,
            format=getattr(args, 'format', None),
            product_dir=getattr(args, 'product_dir', False),
            reverse=getattr(args, 'newest_first', False),
        )

        # Report results
        if result.errors:
            for error in result.errors:
                print(f"Error: {error}", file=sys.stderr)

        report_failed_days(result.failed_days)
        if result.errors or result.failed_days:
            return EXIT_TRANSIENT
        return 0

    except InvalidRequestError as e:
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_NON_TRANSIENT
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return classify_exit_code(e)


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
    from maap_client.paths import baseline_error

    # The collection in each path decides its mission, whatever the active mission
    config = MaapConfig.load(getattr(args, "config", None))
    extra_collections = config.extra_collections()

    # Collect paths to mark
    items = []
    if args.file:
        try:
            with open(args.file, "r") as f:
                items = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        except OSError as e:
            print(f"Error: {e}", file=sys.stderr)
            return EXIT_NON_TRANSIENT
    if args.paths:
        items.extend(args.paths)

    if not items:
        print("No paths provided", file=sys.stderr)
        return EXIT_NON_TRANSIENT

    # Group items by (mission, collection, product, baseline)
    items_by_key: dict[tuple[str, str, str, str], list[str]] = {}

    for item in items:
        parsed = parse_product(item)
        if parsed is None or parsed.product_type is None:
            print(f"Error: cannot parse path: {item}", file=sys.stderr)
            return EXIT_NON_TRANSIENT
        if parsed.baseline is None:
            print(f"Error: {baseline_error(item, parsed)}", file=sys.stderr)
            return EXIT_NON_TRANSIENT

        # Extract collection from path parts (a collection of any mission)
        collection = None
        for part in Path(item).parts:
            if mission_for_collection(part, extra_collections):
                collection = part
                break
        if collection is None:
            print(f"Error: cannot extract collection from path: {item}", file=sys.stderr)
            return EXIT_NON_TRANSIENT

        mission, _ = resolve_mission(collection, [], getattr(args, "mission", None), config)
        key = (mission.name, collection, parsed.product_type, parsed.baseline)

        if key not in items_by_key:
            items_by_key[key] = []
        items_by_key[key].append(item)

    # Process each group
    marked = 0
    failed = 0

    clients: dict[str, MaapClient] = {}
    for (mission_name, collection, product, baseline), paths in items_by_key.items():
        if mission_name not in clients:
            clients[mission_name] = mission_client(args, mission_name)
        tracker = clients[mission_name].get_tracker(collection, product, baseline)

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


def cmd_token(args: argparse.Namespace) -> int:
    """Handle 'token' command - show when the offline token expires."""
    from datetime import datetime, timezone
    from maap_client.auth import load_credentials, offline_token_expiry

    config = MaapConfig.load(args.config) if args.config else MaapConfig.load()
    expiry = offline_token_expiry(load_credentials(config.credentials_file))
    days_left = (expiry - datetime.now(timezone.utc)).days
    if args.days_left:
        print(days_left)
    else:
        print(f"Offline token expires {expiry:%Y-%m-%d %H:%M} UTC ({days_left} days left)")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    """Handle 'config' command - show loaded configuration."""
    config, source = load_config(args)

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
    print(f"mission_source:    {source}")
    print(f"default_formats:   {', '.join(config.default_formats)}")

    # Show config file location
    config_path = Path("~/.maap/config.toml").expanduser()
    if config_path.exists():
        print(f"\nConfig file: {config_path}")
    else:
        print("\nConfig file: not found (using defaults)")

    return 0


def cmd_mission_list(args: argparse.Namespace) -> int:
    """Handle 'mission list' - known missions, marking the active one and its source."""
    config, source = load_config(args)
    for name in MISSIONS:
        if name == config.mission:
            print(f"* {name} ({source})")
        else:
            print(f"  {name}")
    return 0


def cmd_mission_use(args: argparse.Namespace) -> int:
    """Handle 'mission use NAME' - persist the active mission."""
    try:
        name = get_mission(args.name).name
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_NON_TRANSIENT
    try:
        write_active_mission(name)
    except OSError as e:
        print(f"Error: cannot save the active mission: {e}", file=sys.stderr)
        return EXIT_NON_TRANSIENT
    print(f"Active mission: {name}")
    env_mission = os.environ.get("MAAP_MISSION")
    if env_mission and env_mission.lower() != name.lower():
        print(f"Note: MAAP_MISSION={env_mission} takes precedence in this environment", file=sys.stderr)
    return 0


def cmd_mission_show(args: argparse.Namespace) -> int:
    """Handle 'mission show [NAME]' - effective profile of a mission."""
    if args.name:
        try:
            name = get_mission(args.name).name
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return EXIT_NON_TRANSIENT
        config = MaapConfig.load(args.config, mission=name)
    else:
        config, _ = load_config(args)
    filters = ", ".join(map(option_flag, get_mission(config.mission).available_filters()))

    print(f"mission:           {config.mission}")
    print(f"mission_start:     {config.mission_start}")
    print(f"mission_end:       {config.mission_end}")
    print(f"default_formats:   {', '.join(config.default_formats)}")
    print(f"filters:           {filters}")
    print("collections:")
    for collection in config.collections:
        print(f"  {collection}")
    return 0
