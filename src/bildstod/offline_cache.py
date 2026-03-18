#!/usr/bin/env python3
"""Offline cache management for Bildstöd ARASAAC pictograms.

Provides intelligent caching and offline functionality for pictogram access.
"""

import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set
from urllib.error import URLError
from urllib.request import Request, urlopen

import gettext
_ = gettext.gettext

from bildstod.library import get_images_dir


class OfflineCache:
    """Manages offline cache for ARASAAC pictograms."""
    
    def __init__(self, cache_dir=None):
        if cache_dir is None:
            cache_dir = Path(get_images_dir()) / "cache"
        
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.db_path = self.cache_dir / "pictogram_cache.db"
        self.images_dir = self.cache_dir / "images"
        self.images_dir.mkdir(exist_ok=True)
        
        self._init_db()
        self._is_online = None
        self._check_online_thread()
    
    def _init_db(self):
        """Initialize SQLite database for cache metadata."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pictograms (
                    id TEXT PRIMARY KEY,
                    keywords TEXT,
                    swedish_keyword TEXT,
                    cached_at TEXT,
                    access_count INTEGER DEFAULT 1,
                    last_accessed TEXT,
                    file_size INTEGER,
                    available_offline INTEGER DEFAULT 1
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS search_cache (
                    query_hash TEXT PRIMARY KEY,
                    query TEXT,
                    results TEXT,
                    cached_at TEXT,
                    language TEXT
                )
            """)
    
    def _check_online_thread(self):
        """Check internet connectivity in background."""
        def check():
            try:
                req = Request("https://api.arasaac.org/v1/health", 
                            headers={"User-Agent": "Bildstod/0.4.8"})
                with urlopen(req, timeout=5) as _:
                    self._is_online = True
            except (URLError, Exception):
                self._is_online = False
        
        thread = threading.Thread(target=check, daemon=True)
        thread.start()
    
    def is_online(self) -> Optional[bool]:
        """Check if internet connection is available."""
        return self._is_online
    
    def is_pictogram_cached(self, pictogram_id: str, size: int = 500) -> bool:
        """Check if pictogram is available in offline cache."""
        image_path = self.images_dir / f"arasaac_{pictogram_id}_{size}.png"
        return image_path.exists()
    
    def get_cached_path(self, pictogram_id: str, size: int = 500) -> Optional[str]:
        """Get path to cached pictogram image."""
        image_path = self.images_dir / f"arasaac_{pictogram_id}_{size}.png"
        if image_path.exists():
            # Update access statistics
            self._update_access_stats(pictogram_id)
            return str(image_path)
        return None
    
    def cache_pictogram(self, pictogram_id: str, image_data: bytes, 
                       size: int = 500, keywords: List[str] = None,
                       swedish_keyword: str = None) -> str:
        """Cache pictogram image and metadata."""
        image_path = self.images_dir / f"arasaac_{pictogram_id}_{size}.png"
        
        # Save image
        with open(image_path, "wb") as f:
            f.write(image_data)
        
        # Save metadata
        keywords_json = json.dumps(keywords) if keywords else "[]"
        now = datetime.now().isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO pictograms 
                (id, keywords, swedish_keyword, cached_at, last_accessed, 
                 file_size, available_offline)
                VALUES (?, ?, ?, ?, ?, ?, 1)
            """, (pictogram_id, keywords_json, swedish_keyword, 
                  now, now, len(image_data)))
        
        return str(image_path)
    
    def _update_access_stats(self, pictogram_id: str):
        """Update access statistics for pictogram."""
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE pictograms 
                SET access_count = access_count + 1, last_accessed = ?
                WHERE id = ?
            """, (now, pictogram_id))
    
    def cache_search_results(self, query: str, results: List[Dict], 
                           language: str = "sv"):
        """Cache search results for offline access."""
        import hashlib
        query_hash = hashlib.md5(f"{query}:{language}".encode()).hexdigest()
        
        results_json = json.dumps(results)
        now = datetime.now().isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO search_cache
                (query_hash, query, results, cached_at, language)
                VALUES (?, ?, ?, ?, ?)
            """, (query_hash, query, results_json, now, language))
    
    def get_cached_search(self, query: str, language: str = "sv", 
                         max_age_hours: int = 24) -> Optional[List[Dict]]:
        """Get cached search results if available and fresh."""
        import hashlib
        query_hash = hashlib.md5(f"{query}:{language}".encode()).hexdigest()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT results, cached_at FROM search_cache
                WHERE query_hash = ?
            """, (query_hash,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            results_json, cached_at_str = row
            cached_at = datetime.fromisoformat(cached_at_str)
            
            # Check if cache is fresh enough
            if datetime.now() - cached_at > timedelta(hours=max_age_hours):
                return None
            
            return json.loads(results_json)
    
    def get_popular_pictograms(self, limit: int = 100) -> List[str]:
        """Get most frequently accessed pictograms for preloading."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT id FROM pictograms
                ORDER BY access_count DESC, last_accessed DESC
                LIMIT ?
            """, (limit,))
            return [row[0] for row in cursor.fetchall()]
    
    def preload_popular_pictograms(self, callback=None):
        """Preload popular pictograms in background."""
        from bildstod.arasaac import download_image
        
        def preload():
            popular = self.get_popular_pictograms(50)
            total = len(popular)
            
            for i, pictogram_id in enumerate(popular):
                if not self.is_pictogram_cached(pictogram_id):
                    try:
                        download_image(pictogram_id, 
                                     dest_dir=str(self.images_dir))
                        if callback:
                            callback(i + 1, total, pictogram_id)
                    except Exception:
                        pass
        
        thread = threading.Thread(target=preload, daemon=True)
        thread.start()
    
    def cleanup_old_cache(self, max_age_days: int = 30, 
                         keep_popular_count: int = 200):
        """Remove old cached images while keeping popular ones."""
        cutoff_date = datetime.now() - timedelta(days=max_age_days)
        cutoff_str = cutoff_date.isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            # Get pictograms to remove (old and not popular)
            cursor = conn.execute("""
                SELECT id FROM pictograms
                WHERE last_accessed < ? 
                AND id NOT IN (
                    SELECT id FROM pictograms
                    ORDER BY access_count DESC
                    LIMIT ?
                )
            """, (cutoff_str, keep_popular_count))
            
            to_remove = [row[0] for row in cursor.fetchall()]
            
            # Remove files and database entries
            for pictogram_id in to_remove:
                # Remove all sizes of this pictogram
                for size in [300, 500]:
                    image_path = self.images_dir / f"arasaac_{pictogram_id}_{size}.png"
                    if image_path.exists():
                        image_path.unlink()
                
                # Remove database entry
                conn.execute("DELETE FROM pictograms WHERE id = ?", 
                           (pictogram_id,))
            
            # Cleanup old search cache
            conn.execute("DELETE FROM search_cache WHERE cached_at < ?", 
                        (cutoff_str,))
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM pictograms")
            cached_count = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM search_cache")
            search_cache_count = cursor.fetchone()[0]
            
            # Calculate total size
            total_size = 0
            for image_file in self.images_dir.glob("*.png"):
                total_size += image_file.stat().st_size
        
        return {
            "cached_pictograms": cached_count,
            "cached_searches": search_cache_count,
            "total_size_mb": round(total_size / 1024 / 1024, 1),
            "online": self.is_online()
        }


# Global cache instance
_cache = None

def get_cache() -> OfflineCache:
    """Get global cache instance."""
    global _cache
    if _cache is None:
        _cache = OfflineCache()
    return _cache