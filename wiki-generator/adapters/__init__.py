"""Platform adapters for wiki content management."""
from .base import BaseAdapter
from .mediawiki import MediaWikiAdapter
from .confluence import ConfluenceAdapter

__all__ = ['BaseAdapter', 'MediaWikiAdapter', 'ConfluenceAdapter']
