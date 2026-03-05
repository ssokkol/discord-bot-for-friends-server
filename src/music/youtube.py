"""
YouTube извлечение аудио с помощью yt-dlp.
"""

import asyncio
import logging
import re
from typing import Optional, List, Dict, Any
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor

import yt_dlp

from .models import Track, TrackSource

logger = logging.getLogger(__name__)

# Настройки yt-dlp
YTDL_FORMAT_OPTIONS = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False,
    'nocheckcertificate': True,
    'ignoreerrors': True,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'extract_flat': False,
}

# Настройки FFmpeg
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}


class YouTubeExtractor:
    """Класс для извлечения аудио из YouTube"""
    
    # Регулярные выражения для определения типа URL
    YOUTUBE_VIDEO_REGEX = re.compile(
        r'(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)[\w-]+'
    )
    YOUTUBE_PLAYLIST_REGEX = re.compile(
        r'(https?://)?(www\.)?youtube\.com/playlist\?list=[\w-]+'
    )
    
    def __init__(self, max_workers: int = 3):
        self.ytdl = yt_dlp.YoutubeDL(YTDL_FORMAT_OPTIONS)
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._cache: Dict[str, Track] = {}
        self._cache_limit = 100
        
    async def extract_track(self, url_or_query: str) -> Optional[Track]:
        """
        Извлекает информацию о треке по URL или поисковому запросу.
        
        Args:
            url_or_query: URL YouTube видео или поисковый запрос
            
        Returns:
            Track объект или None при ошибке
        """
        # Проверяем кэш
        if url_or_query in self._cache:
            logger.debug(f"Трек найден в кэше: {url_or_query}")
            return self._cache[url_or_query]
        
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(
                self._executor,
                lambda: self._extract_info(url_or_query, download=False)
            )
            
            if not data:
                logger.warning(f"Не удалось получить информацию: {url_or_query}")
                return None
            
            # Если это результат поиска, берем первый результат
            if 'entries' in data:
                entries = [e for e in data['entries'] if e]
                if not entries:
                    return None
                data = entries[0]
            
            track = self._create_track_from_data(data)
            
            # Сохраняем в кэш
            self._add_to_cache(url_or_query, track)
            
            return track
            
        except Exception as e:
            logger.error(f"Ошибка извлечения трека: {e}")
            return None
    
    async def extract_playlist(self, url: str, max_tracks: int = 50) -> List[Track]:
        """
        Извлекает треки из плейлиста YouTube.
        
        Args:
            url: URL плейлиста YouTube
            max_tracks: Максимальное количество треков
            
        Returns:
            Список Track объектов
        """
        try:
            loop = asyncio.get_event_loop()
            
            # Используем flat extraction для быстрого получения списка
            playlist_opts = YTDL_FORMAT_OPTIONS.copy()
            playlist_opts['extract_flat'] = 'in_playlist'
            playlist_opts['playlistend'] = max_tracks
            
            ytdl_playlist = yt_dlp.YoutubeDL(playlist_opts)
            
            data = await loop.run_in_executor(
                self._executor,
                lambda: ytdl_playlist.extract_info(url, download=False)
            )
            
            if not data or 'entries' not in data:
                logger.warning(f"Не удалось получить плейлист: {url}")
                return []
            
            tracks = []
            entries = [e for e in data['entries'] if e][:max_tracks]
            
            # Извлекаем информацию о каждом треке
            for entry in entries:
                video_url = entry.get('url') or f"https://www.youtube.com/watch?v={entry.get('id')}"
                track = await self.extract_track(video_url)
                if track:
                    tracks.append(track)
            
            logger.info(f"Извлечено {len(tracks)} треков из плейлиста")
            return tracks
            
        except Exception as e:
            logger.error(f"Ошибка извлечения плейлиста: {e}")
            return []
    
    async def search(self, query: str, max_results: int = 1) -> List[Track]:
        """
        Поиск треков на YouTube.
        
        Args:
            query: Поисковый запрос
            max_results: Максимальное количество результатов
            
        Returns:
            Список Track объектов
        """
        try:
            search_query = f"ytsearch{max_results}:{query}"
            
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(
                self._executor,
                lambda: self._extract_info(search_query, download=False)
            )
            
            if not data or 'entries' not in data:
                return []
            
            tracks = []
            for entry in data['entries']:
                if entry:
                    track = self._create_track_from_data(entry)
                    tracks.append(track)
            
            return tracks
            
        except Exception as e:
            logger.error(f"Ошибка поиска: {e}")
            return []
    
    async def get_stream_url(self, track: Track) -> Optional[str]:
        """
        Получает URL потока для воспроизведения.
        
        Args:
            track: Track объект
            
        Returns:
            URL аудиопотока или None
        """
        if track.stream_url:
            return track.stream_url
        
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(
                self._executor,
                lambda: self._extract_info(track.url, download=False)
            )
            
            if data and 'url' in data:
                track.stream_url = data['url']
                return data['url']
            
            # Пробуем получить из formats
            if data and 'formats' in data:
                for f in data['formats']:
                    if f.get('acodec') != 'none':
                        track.stream_url = f['url']
                        return f['url']
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка получения stream URL: {e}")
            return None
    
    def is_youtube_url(self, url: str) -> bool:
        """Проверяет, является ли URL ссылкой на YouTube"""
        return bool(self.YOUTUBE_VIDEO_REGEX.match(url) or self.YOUTUBE_PLAYLIST_REGEX.match(url))
    
    def is_playlist_url(self, url: str) -> bool:
        """Проверяет, является ли URL плейлистом YouTube"""
        return bool(self.YOUTUBE_PLAYLIST_REGEX.match(url))
    
    def _extract_info(self, url: str, download: bool = False) -> Optional[Dict[str, Any]]:
        """Синхронное извлечение информации через yt-dlp"""
        try:
            return self.ytdl.extract_info(url, download=download)
        except Exception as e:
            logger.error(f"Ошибка yt-dlp: {e}")
            return None
    
    def _create_track_from_data(self, data: Dict[str, Any]) -> Track:
        """Создает Track из данных yt-dlp"""
        return Track(
            title=data.get('title', 'Unknown'),
            url=data.get('webpage_url') or data.get('url', ''),
            duration=data.get('duration', 0) or 0,
            thumbnail=data.get('thumbnail'),
            artist=data.get('uploader') or data.get('channel'),
            source=TrackSource.YOUTUBE,
            stream_url=data.get('url')
        )
    
    def _add_to_cache(self, key: str, track: Track):
        """Добавляет трек в кэш с ограничением размера"""
        if len(self._cache) >= self._cache_limit:
            # Удаляем первый элемент (FIFO)
            first_key = next(iter(self._cache))
            del self._cache[first_key]
        self._cache[key] = track
    
    def clear_cache(self):
        """Очищает кэш"""
        self._cache.clear()
    
    def __del__(self):
        """Освобождает ресурсы"""
        self._executor.shutdown(wait=False)

