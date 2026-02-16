import threading
import xmlrpc.client
from typing import Any
from xml.etree import ElementTree

import requests

from ..config import Config
from ..validators import validate_content, validate_page_name


class TracClient:
    def __init__(self, config: Config):
        self.config = config
        self._thread_local = threading.local()
        self.rpc_url = self._get_rpc_url()

    @property
    def session(self) -> requests.Session:
        """Backward-compatible accessor for the session (returns current thread's session)."""
        return self._get_session()

    def _get_rpc_url(self) -> str:
        # Construct path to XML-RPC endpoint
        return f"{self.config.trac_url.rstrip('/')}/login/rpc"

    def _get_session(self) -> requests.Session:
        """Get or create a thread-local requests.Session."""
        if not hasattr(self._thread_local, "session"):
            self._thread_local.session = self._create_session()
        return self._thread_local.session

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        session.auth = (self.config.username, self.config.password)
        session.verify = not self.config.insecure
        return session

    def _rpc_request(self, service: str, method: str, *params):
        """
        Make an XML-RPC request to the Trac server.
        """
        payload = xmlrpc.client.dumps(
            params, methodname=f"{service}.{method}"
        )

        headers = {"Content-Type": "text/xml"}
        session = self._get_session()
        response = session.post(
            self.rpc_url,
            data=payload,
            headers=headers,
            timeout=(10, 60),
        )
        response.raise_for_status()

        # Parse the response
        tree = ElementTree.fromstring(response.content)
        fault = tree.find(".//fault")
        if fault is not None:
            fault_code_element = fault.find(
                './/member[name="faultCode"]/value/int'
            )
            fault_string_element = fault.find(
                './/member[name="faultString"]/value/string'
            )
            fault_code = (
                int(fault_code_element.text)
                if fault_code_element is not None
                and fault_code_element.text is not None
                else 0
            )
            fault_string = (
                fault_string_element.text
                if fault_string_element is not None
                and fault_string_element.text is not None
                else "Unknown error"
            )
            raise xmlrpc.client.Fault(fault_code, fault_string)

        # Extract the value from the response
        value_element = tree.find(".//param/value")
        return self._parse_xmlrpc_value(value_element)

    def _parse_xmlrpc_value(self, element):
        """
        Recursively parse an XML-RPC value element.
        """
        data_type = element[0].tag
        data_value = element[0].text

        match data_type:
            case "array":
                data_element = element.find("./array/data")
                if data_element is not None:
                    return [
                        self._parse_xmlrpc_value(v)
                        for v in data_element.findall("value")
                    ]
                return []
            case "struct":
                result = {}
                for member in element.findall(".//member"):
                    name = member.find("name").text
                    value = self._parse_xmlrpc_value(
                        member.find("value")
                    )
                    result[name] = value
                return result
            case "int" | "i4":
                return int(data_value)
            case "boolean":
                return data_value == "1"
            case "string":
                return data_value
            case "double":
                return float(data_value)
            case _:
                return data_value

    def search_tickets(self, query: str) -> Any:
        """
        Search for tickets using a query string.
        """
        return self._rpc_request("ticket", "query", query)

    def get_ticket(self, ticket_id: int) -> Any:
        """
        Get ticket details by ticket ID.
        """
        return self._rpc_request("ticket", "get", ticket_id)

    def get_ticket_changelog(self, ticket_id: int) -> Any:
        """
        Get ticket changelog by ticket ID.
        """
        return self._rpc_request("ticket", "changeLog", ticket_id)

    def validate_connection(self) -> str:
        """
        Validate connection by calling system.getAPIVersion().
        Returns the API version string if successful.
        """
        version = self._rpc_request("system", "getAPIVersion")
        return str(version) if version is not None else ""

    def list_methods(self) -> Any:
        """
        List available RPC methods.
        """
        return self._rpc_request("system", "listMethods")

    def create_ticket(
        self,
        summary: str,
        description: str,
        ticket_type: str | None = None,
        attributes: dict[str, Any] | None = None,
        notify: bool = False,
    ) -> int:
        """
        Create a new ticket in Trac.

        Args:
            summary: Ticket title (required)
            description: Ticket body with WikiFormatting (required)
            ticket_type: Ticket type string. If None, uses default from ticket_types.yaml. Any type configured in Trac is valid.
            attributes: Optional fields (priority, milestone, component, owner, cc, keywords)
            notify: Send email notifications

        Returns:
            Ticket ID (int)

        Raises:
            ValueError: If summary or description is empty
            xmlrpc.client.Fault: If server validation fails or permissions denied
        """
        # Validate required fields
        if not summary or not summary.strip():
            raise ValueError("Summary is required and cannot be empty")
        if not description or not description.strip():
            raise ValueError(
                "Description is required and cannot be empty"
            )

        # Use hardcoded default ticket type (standalone server, no YAML config)
        if ticket_type is None:
            ticket_type = "defect"

        attrs: dict[str, Any] = attributes.copy() if attributes else {}
        attrs["type"] = ticket_type

        result = self._rpc_request(
            "ticket", "create", summary, description, attrs, notify
        )
        return int(result)

    def update_ticket(
        self,
        ticket_id: int,
        comment: str = "",
        attributes: dict[str, Any] | None = None,
        notify: bool = False,
    ) -> list[Any]:
        """
        Update an existing ticket with optimistic locking.

        Args:
            ticket_id: Ticket number to update
            comment: Comment to add (supports WikiFormatting, max 10000 chars)
            attributes: Fields to update (status, priority, owner, resolution, etc.)
            notify: Send email notifications

        Returns:
            Updated ticket data [id, created, modified, attributes]

        Raises:
            ValueError: If comment exceeds 10000 characters
            xmlrpc.client.Fault: If ticket not found, validation fails, or concurrent update
        """
        # Validate comment length
        if comment and len(comment) > 10000:
            raise ValueError(
                "Comment exceeds maximum length of 10000 characters"
            )

        # Get current state for optimistic locking timestamp
        ticket_data = self._rpc_request("ticket", "get", ticket_id)
        if not isinstance(ticket_data, list) or len(ticket_data) < 4:
            raise ValueError("Invalid ticket data format from server")
        current_attrs = ticket_data[
            3
        ]  # [id, created, modified, {attributes}]
        if not isinstance(current_attrs, dict):
            raise ValueError(
                "Invalid ticket attributes format from server"
            )

        # Build update attributes with timestamp
        update_attrs: dict[str, Any] = (
            attributes.copy() if attributes else {}
        )
        update_attrs["_ts"] = current_attrs["_ts"]

        # Default action to "leave" for simple field updates (no workflow transition)
        if "action" not in update_attrs:
            update_attrs["action"] = "leave"

        result = self._rpc_request(
            "ticket", "update", ticket_id, comment, update_attrs, notify
        )
        return result

    def get_ticket_actions(self, ticket_id: int) -> list[Any]:
        """
        Get available workflow actions for a ticket's current state.

        Args:
            ticket_id: Ticket number to get actions for

        Returns:
            List of action tuples [action_name, label, hints, input_fields]
            where hints contains allowed status transitions

        Raises:
            xmlrpc.client.Fault: If ticket not found or method not available
        """
        result = self._rpc_request("ticket", "getActions", ticket_id)
        return result

    def list_wiki_pages(self) -> list[str]:
        """
        List all wiki page names in Trac.

        Returns:
            List of wiki page names (e.g., ["WikiStart", "UserGuide", "API/Reference"])

        Raises:
            xmlrpc.client.Fault: If server returns error or permissions denied
        """
        result = self._rpc_request("wiki", "getAllPages")
        return result

    def get_wiki_page(
        self, page_name: str, version: int | None = None
    ) -> str:
        """
        Get wiki page content in raw TracWiki format.

        Args:
            page_name: Name of wiki page (e.g., "WikiStart")
            version: Optional version number (default: latest)

        Returns:
            Raw TracWiki markup as string

        Raises:
            xmlrpc.client.Fault: If page not found or permissions denied
        """
        if version is None:
            result = self._rpc_request("wiki", "getPage", page_name)
        else:
            result = self._rpc_request(
                "wiki", "getPageVersion", page_name, version
            )
        return result

    def get_wiki_page_info(
        self, page_name: str, version: int | None = None
    ) -> dict[str, Any]:
        """
        Get wiki page metadata.

        Args:
            page_name: Name of wiki page
            version: Optional version number (default: latest)

        Returns:
            Dict with keys: name, author, version, lastModified

        Raises:
            xmlrpc.client.Fault: If page not found or permissions denied
        """
        if version is None:
            result = self._rpc_request("wiki", "getPageInfo", page_name)
        else:
            result = self._rpc_request(
                "wiki", "getPageInfoVersion", page_name, version
            )
        return result

    def get_wiki_page_with_metadata(
        self, page_name: str
    ) -> dict[str, Any]:
        """
        Get wiki page content with full metadata.
        This method provides helpful error messages with suggestions for missing pages.

        Args:
            page_name: Name of wiki page

        Returns:
            Dict with keys: name, content, version, author, lastModified

        Raises:
            ValueError: If page not found, includes suggestions for similar pages
            xmlrpc.client.Fault: For other server errors
        """
        try:
            content = self.get_wiki_page(page_name)
            info = self.get_wiki_page_info(page_name)

            return {
                "name": page_name,
                "content": content,
                "version": info.get("version"),
                "author": info.get("author"),
                "lastModified": info.get("lastModified"),
            }
        except xmlrpc.client.Fault as err:
            if err.faultCode == 1:  # Page not found
                # Find similar pages by substring matching
                all_pages = self.list_wiki_pages()
                query_lower = page_name.lower()
                suggestions = [
                    p for p in all_pages if query_lower in p.lower()
                ][:5]

                suggestion_text = ""
                if suggestions:
                    suggestion_text = (
                        f" Similar pages: {', '.join(suggestions)}"
                    )

                raise ValueError(
                    f"Page '{page_name}' not found.{suggestion_text}"
                ) from None
            else:
                # Re-raise other faults
                raise

    def search_wiki_pages_by_title(
        self, query: str, max_results: int = 10
    ) -> list[dict[str, Any]]:
        """
        Search wiki pages by title using substring matching.

        Args:
            query: Search string (case-insensitive substring match)
            max_results: Maximum number of results to return (default: 10)

        Returns:
            List of dicts with keys: name, snippet (matched portion of title)

        Raises:
            xmlrpc.client.Fault: If server returns error
        """
        all_pages = self.list_wiki_pages()
        query_lower = query.lower()
        matches = []

        for page_name in all_pages:
            if query_lower in page_name.lower():
                # Find match position for snippet
                match_pos = page_name.lower().index(query_lower)
                snippet_start = max(0, match_pos - 20)
                snippet_end = min(
                    len(page_name), match_pos + len(query) + 20
                )
                snippet = page_name[snippet_start:snippet_end]

                matches.append({"name": page_name, "snippet": snippet})

                if len(matches) >= max_results:
                    break

        return matches

    def search_wiki_pages_by_content(
        self, query: str, max_results: int = 10
    ) -> list[dict[str, Any]]:
        """
        Search wiki pages by content (full-text search).

        Args:
            query: Search string (case-insensitive)
            max_results: Maximum number of results to return (default: 10)

        Returns:
            List of dicts with keys: name, snippet (matching context ~100 chars)

        Raises:
            xmlrpc.client.Fault: If server returns error when listing pages
        """
        all_pages = self.list_wiki_pages()
        query_lower = query.lower()
        matches = []

        for page_name in all_pages:
            try:
                content = self.get_wiki_page(page_name)
                content_lower = content.lower()

                if query_lower in content_lower:
                    # Extract snippet around match (~100 chars)
                    match_pos = content_lower.index(query_lower)
                    snippet_start = max(0, match_pos - 50)
                    snippet_end = min(
                        len(content), match_pos + len(query) + 50
                    )
                    snippet = content[snippet_start:snippet_end].strip()

                    # Add ellipsis if truncated
                    if snippet_start > 0:
                        snippet = "..." + snippet
                    if snippet_end < len(content):
                        snippet = snippet + "..."

                    matches.append(
                        {"name": page_name, "snippet": snippet}
                    )

                    if len(matches) >= max_results:
                        break
            except Exception:
                # Skip pages that can't be read (permission denied, etc.)
                continue

        return matches

    def put_wiki_page(
        self,
        page_name: str,
        content: str,
        comment: str,
        version: int | None = None,
    ) -> dict[str, Any]:
        """
        Create or update a wiki page with optimistic locking.

        Args:
            page_name: Name of the wiki page to create/update
            content: Page content in TracWiki format
            comment: Comment describing the change
            version: Optional version number for optimistic locking (prevents concurrent edits)

        Returns:
            Dict with keys: name, version, author, lastModified, url

        Raises:
            ValueError: If page_name or content validation fails, or version conflict detected
            xmlrpc.client.Fault: If server returns error or permissions denied
        """
        # Validate page name
        is_valid, error_msg = validate_page_name(page_name)
        if not is_valid:
            raise ValueError(f"Invalid page name: {error_msg}")

        # Validate content
        is_valid, error_msg = validate_content(content)
        if not is_valid:
            raise ValueError(f"Invalid content: {error_msg}")

        # Build attributes dict
        attrs: dict[str, Any] = {"comment": comment}
        if version is not None:
            attrs["version"] = version

        # Make the RPC call
        try:
            result = self._rpc_request(
                "wiki", "putPage", page_name, content, attrs
            )

            # If successful, get updated page info
            if result is True:
                info = self.get_wiki_page_info(page_name)

                # Construct URL from config
                page_url = f"{self.config.trac_url.rstrip('/')}/wiki/{page_name}"

                return {
                    "name": page_name,
                    "version": info.get("version"),
                    "author": info.get("author"),
                    "lastModified": info.get("lastModified"),
                    "url": page_url,
                }
            else:
                raise ValueError(f"Failed to update page '{page_name}'")

        except xmlrpc.client.Fault as err:
            # Handle specific fault conditions
            fault_str = err.faultString.lower()

            if "not modified" in fault_str:
                raise ValueError(
                    "Page not modified (content identical)"
                ) from None
            elif "version" in fault_str:
                raise ValueError(
                    "Version conflict - page was modified by another user"
                ) from None
            else:
                # Re-raise other faults
                raise

    def get_wiki_page_html(
        self, page_name: str, version: int | None = None
    ) -> str:
        """
        Get rendered HTML for a wiki page.

        Args:
            page_name: Name of wiki page
            version: Optional version number (default: latest)

        Returns:
            Rendered HTML as string

        Raises:
            xmlrpc.client.Fault: If page not found or permissions denied
        """
        if version is None:
            result = self._rpc_request("wiki", "getPageHTML", page_name)
        else:
            result = self._rpc_request(
                "wiki", "getPageHTMLVersion", page_name, version
            )
        return result

    def delete_wiki_page(self, page_name: str) -> bool:
        """
        Delete a wiki page.

        Args:
            page_name: Name of wiki page to delete

        Returns:
            True if successful

        Raises:
            xmlrpc.client.Fault: If page not found or permissions denied
        """
        result = self._rpc_request("wiki", "deletePage", page_name)
        return result

    def get_recent_wiki_changes(
        self, since_timestamp: int = 0
    ) -> list[dict[str, Any]]:
        """
        Get recently modified wiki pages.

        Args:
            since_timestamp: Unix timestamp (seconds since epoch). Returns pages modified since this time.
                           Default 0 returns all recent changes.

        Returns:
            List of change dicts with keys: name, author, lastModified, version
            Sorted by modification date (newest first)

        Raises:
            xmlrpc.client.Fault: If method not available or permissions denied
        """
        try:
            # Try getRecentChanges if available
            dt = xmlrpc.client.DateTime(since_timestamp)
            result = self._rpc_request("wiki", "getRecentChanges", dt)
            return result
        except xmlrpc.client.Fault as e:
            # Fall back to getAllPages + getPageInfo if getRecentChanges not available
            if (
                "not found" in str(e).lower()
                or "no such method" in str(e).lower()
            ):
                pages = self.list_wiki_pages()
                changes = []
                for page in pages:
                    try:
                        info = self.get_wiki_page_info(page)
                        # Filter by timestamp if provided
                        last_modified = info.get("lastModified", 0)
                        if isinstance(
                            last_modified, xmlrpc.client.DateTime
                        ):
                            # Convert DateTime to timestamp
                            import time

                            last_modified = int(
                                time.mktime(last_modified.timetuple())
                            )
                        if (
                            since_timestamp == 0
                            or last_modified >= since_timestamp
                        ):
                            changes.append(info)
                    except Exception:
                        continue
                # Sort by lastModified descending
                changes.sort(
                    key=lambda x: x.get("lastModified", 0), reverse=True
                )
                return changes
            raise

    # Milestone operations

    def get_all_milestones(self) -> list[str]:
        """
        List all milestone names in Trac.

        Returns:
            List of milestone names (e.g., ["v1.0", "v2.0", "Future"])

        Raises:
            xmlrpc.client.Fault: If server returns error or permissions denied (requires TICKET_VIEW)
        """
        result = self._rpc_request("ticket.milestone", "getAll")
        return result

    def get_milestone(self, name: str) -> dict[str, Any]:
        """
        Get milestone details by name.

        Args:
            name: Milestone name

        Returns:
            Dict with keys: name, due (DateTime or 0), completed (DateTime or 0), description

        Raises:
            xmlrpc.client.Fault: If milestone not found or permissions denied (requires TICKET_VIEW)
        """
        result = self._rpc_request("ticket.milestone", "get", name)
        return result

    def create_milestone(
        self, name: str, attributes: dict[str, Any]
    ) -> None:
        """
        Create a new milestone.

        Args:
            name: Milestone name
            attributes: Dict with optional keys: due (DateTime), completed (DateTime or 0), description (str)

        Raises:
            xmlrpc.client.Fault: If milestone exists, validation fails, or permissions denied (requires TICKET_ADMIN)
        """
        self._rpc_request(
            "ticket.milestone", "create", name, attributes
        )

    def update_milestone(
        self, name: str, attributes: dict[str, Any]
    ) -> None:
        """
        Update an existing milestone.

        Args:
            name: Milestone name
            attributes: Dict with keys to update: due (DateTime), completed (DateTime or 0), description (str)

        Raises:
            xmlrpc.client.Fault: If milestone not found, validation fails, or permissions denied (requires TICKET_ADMIN)
        """
        self._rpc_request(
            "ticket.milestone", "update", name, attributes
        )

    def delete_milestone(self, name: str) -> None:
        """
        Delete a milestone.

        Args:
            name: Milestone name

        Raises:
            xmlrpc.client.Fault: If milestone not found or permissions denied (requires TICKET_ADMIN)
        """
        self._rpc_request("ticket.milestone", "delete", name)

    # Ticket field metadata

    def delete_ticket(self, ticket_id: int) -> bool:
        """
        Delete a ticket.

        Args:
            ticket_id: Ticket number to delete

        Returns:
            True if successful

        Raises:
            xmlrpc.client.Fault: If ticket not found or permissions denied (requires TICKET_ADMIN)
        """
        self._rpc_request("ticket", "delete", ticket_id)
        # Server returns 0 (int) on success; errors raise xmlrpc.client.Fault.
        # Return True explicitly to match documented bool return type.
        return True

    def get_ticket_fields(self) -> list[dict[str, Any]]:
        """
        Get all ticket field definitions (standard + custom fields).

        Returns:
            List of dicts with keys: name, type, label, options (for select fields), custom (bool)

        Raises:
            xmlrpc.client.Fault: If server returns error or permissions denied (requires TICKET_VIEW)
        """
        result = self._rpc_request("ticket", "getTicketFields")
        return result
