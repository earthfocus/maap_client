"""Base catalog class for MAAP data structures."""

from __future__ import annotations

import json
import types
from datetime import datetime
from pathlib import Path
from typing import Any, Union, get_args, get_origin, get_type_hints

from maap_client.utils import parse_datetime, to_zulu


class Catalog:
    """
    Base class for all catalog objects with automatic serialization.

    Provides a foundation for catalog data structures with:
    - Automatic JSON serialization/deserialization via to_dict()/from_dict()
    - Type-aware conversion (datetime, nested Catalog objects, etc.)

    Class Attributes:
        SORT_KEYS: If True, dictionary keys are sorted alphabetically in
            to_dict() output. Default: True.
        DEDUPE_STR_LISTS: If True, duplicate strings are removed from lists
            during serialization. Default: False.
        SORT_NESTED_KEYS: List of key names whose dict contents should be
            sorted, even when SORT_KEYS is False. Default: [].
    """

    # Policy knobs (override in subclasses)
    SORT_KEYS: bool = True
    DEDUPE_STR_LISTS: bool = False
    SORT_NESTED_KEYS: list[str] = []  # Keys whose dict contents should be sorted

    def __init__(self, **kwargs: Any):
        """
        Initialize catalog from keyword arguments.

        Args:
            **kwargs: Field values stored as direct attributes.
        """
        for key, value in kwargs.items():
            setattr(self, key, value)

    def to_dict(
        self,
        *,
        sort_keys: bool | None = None,
        dedupe_str_lists: bool | None = None,
    ) -> dict[str, Any]:
        """
        Convert catalog object to dictionary for JSON serialization.

        Recursively converts:
        - Catalog subclasses → their to_dict() result
        - datetime → ISO 8601 Zulu format string
        - dict → recursively converted values
        - list → recursively converted elements

        Private attributes (starting with _) are excluded.

        Args:
            sort_keys: Sort dictionary keys alphabetically.
                Defaults to class SORT_KEYS.
            dedupe_str_lists: Remove duplicates from string-only lists.
                Defaults to class DEDUPE_STR_LISTS.

        Returns:
            Dictionary suitable for JSON serialization.
        """
        sort_keys = self.SORT_KEYS if sort_keys is None else sort_keys
        dedupe_str_lists = self.DEDUPE_STR_LISTS if dedupe_str_lists is None else dedupe_str_lists

        sort_nested_keys = self.SORT_NESTED_KEYS

        def convert_value(value: Any, key: str | None = None) -> Any:
            """Recursively convert any value type."""

            # Catalog subclass
            if isinstance(value, Catalog):
                return value.to_dict(sort_keys=sort_keys, dedupe_str_lists=dedupe_str_lists)
            # Datetime
            if isinstance(value, datetime):
                return to_zulu(value)
            # Dict (recursive)
            if isinstance(value, dict):
                items = value.items()
                # Sort if sort_keys is True OR if this key is in SORT_NESTED_KEYS
                should_sort = sort_keys or (key is not None and key in sort_nested_keys)
                if should_sort:
                    items = sorted(items, key=lambda kv: kv[0])
                return {k: convert_value(v, key=k) for k, v in items}
            # List (recursive, supports list-of-dicts, list-of-lists, etc.)
            if isinstance(value, list):
                converted_list = [convert_value(v, key=key) for v in value]

                # Optional: dedupe only when *all* elements are strings (and list is non-empty)
                if (
                    dedupe_str_lists
                    and converted_list
                    and all(isinstance(v, str) for v in converted_list)
                ):
                    return list(dict.fromkeys(converted_list))  # stable de-dupe

                return converted_list
            # Everything else
            return value

        # Serialize public attrs
        result: dict[str, Any] = {}

        attrs_items = self.__dict__.items()
        if sort_keys:
            attrs_items = sorted(attrs_items, key=lambda kv: kv[0])

        for key, val in attrs_items:
            if key.startswith("_"):
                continue
            result[key] = convert_value(val, key=key)

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Catalog:
        """
        Create catalog instance from dictionary with automatic type conversion.

        Uses __init__ type hints to determine target types:
        - str → datetime (if hint is datetime)
        - dict → Catalog subclass (if hint is Catalog subclass)
        - dict[str, T] → recursively convert values to T
        - list[T] → recursively convert elements to T
        - Optional[T] → unwraps to T for conversion

        Args:
            data: Dictionary to convert (typically from JSON).

        Returns:
            New instance of the catalog class.
        """
        try:
            hints = get_type_hints(cls.__init__)
        except Exception:
            return cls(**data)

        # hints to determine target type
        def strip_optional(hint: Any) -> Any:
            """Handle Optional[T] and T | None (Python 3.10+)."""
            origin = get_origin(hint)
            if origin is Union or origin is getattr(types, "UnionType", None):
                args = [arg for arg in get_args(hint) if arg is not type(None)]
                return args[0] if len(args) == 1 else hint
            return hint

        def convert_value(value: Any, hint: Any) -> Any:
            """Recursively convert a value based on its type hint."""
            if value is None:
                return None

            hint = strip_optional(hint)
            origin = get_origin(hint)

            # Datetime
            if hint == datetime and isinstance(value, str):
                return parse_datetime(value)
            # Catalog subclass
            if isinstance(hint, type) and issubclass(hint, Catalog) and isinstance(value, dict):
                return hint.from_dict(value)
            # dict[str, T] - recursively convert values
            if origin == dict and isinstance(value, dict):
                args = get_args(hint)
                if len(args) == 2:
                    value_hint = args[1]
                    items = sorted(value.items()) if cls.SORT_KEYS else value.items()
                    return {k: convert_value(v, value_hint) for k, v in items}
                return value
            # list[T] - recursively convert elements
            if origin == list and isinstance(value, list):
                args = get_args(hint)
                if args:
                    elem_hint = args[0]
                    converted_list = [convert_value(item, elem_hint) for item in value]

                    # Optional: dedupe only when all elements are strings
                    if (
                        cls.DEDUPE_STR_LISTS
                        and converted_list
                        and all(isinstance(v, str) for v in converted_list)
                    ):
                        return list(dict.fromkeys(converted_list))

                    return converted_list
                return value
            # Everything else
            return value

        converted: dict[str, Any] = {}
        for key, value in data.items():
            if key in hints:
                converted[key] = convert_value(value, hints[key])
            else:
                converted[key] = value

        return cls(**converted)

    def __repr__(self) -> str:
        attrs = ", ".join(
            f"{k}={v!r}" for k, v in self.__dict__.items() if not k.startswith("_")
        )
        return f"{self.__class__.__name__}({attrs})"


class CatalogManager:
    """
    Base class for catalog managers with file persistence and caching.

    Provides a unified interface for loading, saving, and caching catalog
    objects on disk. Subclasses define the specific catalog type and file
    naming convention.

    Subclasses must override:
        FILENAME_PATTERN: Format string with {collection} placeholder.
        DEFAULT_DIR: Default directory for catalog files.
        CATALOG_CLASS: The Catalog subclass to instantiate when loading.
    """

    # Subclasses must override these
    FILENAME_PATTERN: str = "{collection}.json"
    DEFAULT_DIR: Path = Path(".")
    CATALOG_CLASS: type[Catalog]

    def __init__(self, catalog_dir: Path | None = None):
        self._catalog_dir = catalog_dir or self.DEFAULT_DIR
        self._cache: dict[str, Catalog] = {}

    def get_path(self, collection: str) -> Path:
        """Get file path for a collection's catalog."""
        return self._catalog_dir / self.FILENAME_PATTERN.format(collection=collection)

    def load(self, collection: str) -> Catalog | None:
        """Load catalog from disk with caching."""
        if collection in self._cache:
            return self._cache[collection]

        path = self.get_path(collection)
        if not path.exists():
            return None

        with open(path, "r") as f:
            catalog = self.CATALOG_CLASS.from_dict(json.load(f))

        self._cache[collection] = catalog
        return catalog

    def save(self, catalog: Catalog) -> Path:
        """Save catalog to disk and update cache."""
        path = self.get_path(catalog.collection)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(catalog.to_dict(), f, indent=2)
        self._cache[catalog.collection] = catalog
        return path
