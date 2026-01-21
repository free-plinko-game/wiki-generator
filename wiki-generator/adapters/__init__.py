"""Platform adapters for wiki content management."""
from .base import BaseAdapter
from .mediawiki import MediaWikiAdapter

__all__ = ['BaseAdapter', 'MediaWikiAdapter']
