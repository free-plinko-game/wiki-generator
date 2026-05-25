"""Platform adapters for wiki content management."""
from .base import BaseAdapter
from .mediawiki import MediaWikiAdapter
from .confluence import ConfluenceAdapter
from .fandom import FandomAdapter

__all__ = ['BaseAdapter', 'MediaWikiAdapter', 'ConfluenceAdapter', 'FandomAdapter']
