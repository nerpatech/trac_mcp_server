"""
Capability detection for Trac servers.

Orchestrates detection methods and caches results to avoid expensive
detection operations on every run.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class CapabilityDetector:
    """
    Detects Trac server capabilities through multiple methods.

    Detection methods:
    1. XML-RPC system.* methods (fastest, requires XML-RPC enabled)
    2. Web scraping /about page (requires CONFIG_VIEW permission)
    3. Probing techniques (fallback when above methods unavailable)

    Results are cached in .trac_mcp/capabilities.json with 24-hour expiry.
    """

    CACHE_EXPIRY_HOURS = 24

    def __init__(self, trac_client, config):
        """
        Initialize capability detector.

        Args:
            trac_client: TracClient instance for XML-RPC calls
            config: Configuration object (cache enabled if config has project_config_dir attribute)
        """
        self.trac_client = trac_client
        self.config = config

        # Determine cache file path
        if (
            hasattr(config, "project_config_dir")
            and config.project_config_dir
        ):
            self.cache_path = (
                Path(config.project_config_dir) / "capabilities.json"
            )
        else:
            # Fallback: no caching if project config dir not available
            self.cache_path = None
            logger.warning(
                "No project config directory available, caching disabled"
            )

    def detect_all(self, force_refresh: bool = False) -> dict[str, Any]:
        """
        Detect all capabilities using orchestrated detection methods.

        Args:
            force_refresh: If True, bypass cache and re-detect

        Returns:
            Dictionary with capability information:
            {
                "trac_version": str or None,
                "xmlrpc_available": bool,
                "markdown_processor": str or None,  # "mistune", "markdown2", etc.
                "markdown_formatter": str or None,  # "markdown", "text/x-markdown", etc.
                "wiki_processors": list[str],  # ["default", "code", "python", ...]
                "detection_method": str,  # "xmlrpc", "web_scraping", "probing"
                "timestamp": str  # ISO 8601 timestamp
            }
        """
        # Try to load from cache if not forcing refresh
        if not force_refresh:
            cached = self._load_cache()
            if cached:
                logger.info(
                    "Using cached capabilities (expires in %s)",
                    self._format_cache_age(cached.get("timestamp")),
                )
                return cached

        # Initialize capabilities structure
        capabilities = {
            "trac_version": None,
            "xmlrpc_available": False,
            "markdown_processor": None,
            "markdown_formatter": None,
            "wiki_processors": [],
            "available_methods": [],
            "has_wiki_rpc": False,
            "has_ticket_rpc": False,
            "detection_method": "none",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Try XML-RPC detection first (fastest, preferred method)
        xmlrpc_caps = self._detect_via_xmlrpc()
        if xmlrpc_caps.get("xmlrpc_available"):
            capabilities.update(xmlrpc_caps)
            capabilities["detection_method"] = "xmlrpc"
            logger.info(
                "Detected capabilities via XML-RPC: %d methods available",
                len(xmlrpc_caps.get("available_methods", [])),
            )

        # Try web scraping if we don't have version info yet
        if not capabilities.get("trac_version"):
            web_caps = self._detect_via_web()
            if web_caps:
                capabilities.update(web_caps)
                if capabilities["detection_method"] == "none":
                    capabilities["detection_method"] = "web_scraping"
                logger.info(
                    "Detected capabilities via web scraping: Trac %s",
                    web_caps.get("trac_version", "unknown"),
                )

        # Try probing if we still don't have processor info
        if not capabilities.get("wiki_processors"):
            probing_caps = self._detect_via_probing()
            if probing_caps:
                capabilities.update(probing_caps)
                if capabilities["detection_method"] == "none":
                    capabilities["detection_method"] = "probing"
                elif capabilities["detection_method"] != "none":
                    # Combined detection methods
                    capabilities["detection_method"] = (
                        f"{capabilities['detection_method']},probing"
                    )
                logger.info(
                    "Detected capabilities via probing: %d processors found",
                    len(probing_caps.get("wiki_processors", [])),
                )

        # Save to cache
        self._save_cache(capabilities)

        return capabilities

    def _detect_via_xmlrpc(self) -> dict[str, Any]:
        """
        Detect capabilities via XML-RPC system.listMethods().

        Returns:
            Dict with xmlrpc_available, available_methods, has_wiki_rpc, has_ticket_rpc
        """
        try:
            # Get all available XML-RPC methods
            methods = self.trac_client.list_methods()

            if not isinstance(methods, list):
                logger.warning(
                    "system.listMethods() returned unexpected type: %s",
                    type(methods),
                )
                return {"xmlrpc_available": False}

            # Categorize methods by namespace
            has_wiki = any(m.startswith("wiki.") for m in methods)
            has_ticket = any(m.startswith("ticket.") for m in methods)

            logger.debug(
                "XML-RPC detection: %d methods, wiki=%s, ticket=%s",
                len(methods),
                has_wiki,
                has_ticket,
            )

            return {
                "xmlrpc_available": True,
                "available_methods": methods,
                "has_wiki_rpc": has_wiki,
                "has_ticket_rpc": has_ticket,
            }

        except Exception as e:
            # XML-RPC not available or connection failed
            logger.warning("XML-RPC detection failed: %s", e)
            return {"xmlrpc_available": False}

    def _detect_via_web(self) -> dict[str, Any]:
        """
        Detect capabilities via web scraping (fallback method).

        Returns:
            Dict with trac_version, plugins, markdown_processor
        """
        from .web_scraper import scrape_about_page

        try:
            # Scrape /about page for version and plugin info
            auth_tuple = (self.config.username, self.config.password)
            result = scrape_about_page(self.config.trac_url, auth_tuple)

            if result:
                logger.debug(
                    "Web scraping successful: Trac %s, %d plugins",
                    result.get("trac_version", "unknown"),
                    len(result.get("plugins", {})),
                )

            return result

        except Exception as e:
            logger.warning("Web scraping detection failed: %s", e)
            return {}

    def _detect_via_probing(self) -> dict[str, Any]:
        """
        Detect processor availability via probing (final fallback method).

        Tests common processors by creating wiki pages with processor blocks
        and checking if they render without errors.

        Returns:
            Dict with wiki_processors list and markdown_processor bool
        """
        from .processor_utils import check_processor_available

        # Common processors to test
        processors_to_test = ["markdown", "rst", "textile", "html"]
        available_processors = []

        logger.info("Testing processor availability via probing...")

        for processor in processors_to_test:
            try:
                if check_processor_available(
                    self.trac_client, processor
                ):
                    available_processors.append(processor)
                    logger.debug(
                        "Processor '%s' is available", processor
                    )
                else:
                    logger.debug(
                        "Processor '%s' is not available", processor
                    )
            except Exception as e:
                logger.warning(
                    "Failed to test processor '%s': %s", processor, e
                )

        # Check if markdown processor is available
        has_markdown = "markdown" in available_processors

        logger.info(
            "Probing detected %d processors: %s",
            len(available_processors),
            ", ".join(available_processors)
            if available_processors
            else "none",
        )

        return {
            "wiki_processors": available_processors,
            "markdown_processor": has_markdown,
        }

    def _load_cache(self) -> dict[str, Any] | None:
        """
        Load capabilities from cache file if exists and not expired.

        Returns:
            Cached capabilities dict, or None if cache invalid/expired
        """
        if not self.cache_path or not self.cache_path.exists():
            return None

        try:
            with open(self.cache_path, "r") as f:
                cached = json.load(f)

            # Check if cache is expired
            timestamp_str = cached.get("timestamp")
            if not timestamp_str:
                logger.warning(
                    "Cache missing timestamp, treating as expired"
                )
                return None

            try:
                cached_time = datetime.fromisoformat(timestamp_str)
            except ValueError:
                logger.warning(
                    "Invalid timestamp format in cache: %s",
                    timestamp_str,
                )
                return None

            # Ensure timezone-aware comparison
            if cached_time.tzinfo is None:
                cached_time = cached_time.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)
            age = now - cached_time

            if age > timedelta(hours=self.CACHE_EXPIRY_HOURS):
                logger.info(
                    "Cache expired (age: %s), will re-detect", age
                )
                return None

            logger.debug("Cache valid (age: %s)", age)
            return cached

        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load cache: %s", e)
            return None

    def _save_cache(self, capabilities: dict[str, Any]) -> None:
        """
        Save capabilities to cache file.

        Args:
            capabilities: Capabilities dict to cache
        """
        if not self.cache_path:
            logger.debug("Cache path not available, skipping save")
            return

        try:
            # Ensure directory exists
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.cache_path, "w") as f:
                json.dump(capabilities, f, indent=2)

            logger.debug(
                "Saved capabilities to cache: %s", self.cache_path
            )

        except OSError as e:
            logger.warning("Failed to save cache: %s", e)

    def _format_cache_age(self, timestamp_str: str | None) -> str:
        """
        Format cache age for logging.

        Args:
            timestamp_str: ISO 8601 timestamp string

        Returns:
            Human-readable string like "2h 30m" or "expired"
        """
        if not timestamp_str:
            return "unknown"

        try:
            cached_time = datetime.fromisoformat(timestamp_str)
            if cached_time.tzinfo is None:
                cached_time = cached_time.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)
            age = now - cached_time
            expiry = timedelta(hours=self.CACHE_EXPIRY_HOURS) - age

            if expiry.total_seconds() <= 0:
                return "expired"

            hours = int(expiry.total_seconds() // 3600)
            minutes = int((expiry.total_seconds() % 3600) // 60)

            if hours > 0:
                return f"{hours}h {minutes}m"
            else:
                return f"{minutes}m"

        except (ValueError, AttributeError):
            return "unknown"


async def get_server_capabilities(config):
    """
    Convenience function to get server capabilities from config.

    Args:
        config: Config object with trac_url, username, password attributes

    Returns:
        Object with markdown_processor, trac_version, xmlrpc_available, wiki_processors attributes
    """
    from trac_mcp_server.core.client import TracClient

    # Create TracClient instance
    trac_client = TracClient(config)

    # Create detector and get capabilities
    detector = CapabilityDetector(trac_client, config)
    capabilities = detector.detect_all()

    # Convert to simple object for easier attribute access
    class Capabilities:
        def __init__(self, caps_dict):
            self.markdown_processor = bool(
                caps_dict.get("markdown_processor")
            )
            self.trac_version = caps_dict.get("trac_version")
            self.xmlrpc_available = caps_dict.get(
                "xmlrpc_available", False
            )
            self.wiki_processors = caps_dict.get("wiki_processors", [])

    return Capabilities(capabilities)
