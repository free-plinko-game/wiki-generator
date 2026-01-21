"""Base adapter interface for wiki platforms."""
from abc import ABC, abstractmethod
from typing import Optional, Callable


class BaseAdapter(ABC):
    """Abstract base class for wiki platform adapters."""

    @abstractmethod
    def __init__(self, config: dict):
        """Initialize adapter with platform-specific configuration."""
        pass

    @abstractmethod
    def test_connection(self) -> dict:
        """
        Test connection to the platform.

        Returns:
            dict with keys:
                - success: bool
                - site_name: str or None
                - error: str or None
        """
        pass

    @abstractmethod
    def login(self) -> bool:
        """
        Authenticate with the platform.

        Returns:
            True if login successful, False otherwise.
        """
        pass

    @abstractmethod
    def upload_page(self, title: str, content: str) -> bool:
        """
        Upload a single page to the platform.

        Args:
            title: Page title
            content: Page content in platform-native format

        Returns:
            True if upload successful, False otherwise.
        """
        pass

    @abstractmethod
    def upload_directory(
        self,
        content_dir: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> dict:
        """
        Upload all content files from a directory.

        Args:
            content_dir: Path to directory containing content files
            progress_callback: Optional callback(current, total, page_title)

        Returns:
            dict with keys:
                - success: list of uploaded page titles
                - failed: list of failed page titles
        """
        pass

    @abstractmethod
    def get_page(self, title: str) -> Optional[str]:
        """
        Retrieve content of a page.

        Args:
            title: Page title

        Returns:
            Page content or None if not found.
        """
        pass

    @abstractmethod
    def list_pages(self) -> list:
        """
        List all pages on the wiki.

        Returns:
            List of page titles.
        """
        pass

    @staticmethod
    def get_content_extension() -> str:
        """Return the file extension for content files (e.g., '.wiki')."""
        return '.wiki'

    @staticmethod
    def get_platform_name() -> str:
        """Return human-readable platform name."""
        return 'Unknown'
