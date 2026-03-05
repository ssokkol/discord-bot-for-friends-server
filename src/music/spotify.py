"""
Интеграция с Spotify API для получения метаданных треков.
"""

import asyncio
import logging
import re
from typing import Optional, List, Tuple
from concurrent.futures import ThreadPoolExecutor

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from .models import Track, TrackSource
from .youtube import YouTubeExtractor

logger = logging.getLogger(__name__)


class SpotifyClient:
    """Клиент для работы со Spotify API"""
    
    # Регулярные выражения для Spotify URL/URI
    SPOTIFY_TRACK_REGEX = re.compile(
        r'(https?://open\.spotify\.com/track/|spotify:track:)([a-zA-Z0-9]+)'
    )
    SPOTIFY_ALBUM_REGEX = re.compile(
        r'(https?://open\.spotify\.com/album/|spotify:album:)([a-zA-Z0-9]+)'
    )
    SPOTIFY_PLAYLIST_REGEX = re.compile(
        r'(https?://open\.spotify\.com/playlist/|spotify:playlist:)([a-zA-Z0-9]+)'
    )
    
    def __init__(
        self, 
        client_id: str, 
        client_secret: str,
        youtube_extractor: YouTubeExtractor
    ):
        """
        Инициализация клиента Spotify.
        
        Args:
            client_id: Spotify Client ID
            client_secret: Spotify Client Secret
            youtube_extractor: Экземпляр YouTubeExtractor для поиска треков
        """
        self._enabled = bool(client_id and client_secret)
        self._youtube = youtube_extractor
        self._executor = ThreadPoolExecutor(max_workers=2)
        
        if self._enabled:
            try:
                auth_manager = SpotifyClientCredentials(
                    client_id=client_id,
                    client_secret=client_secret
                )
                self._spotify = spotipy.Spotify(auth_manager=auth_manager)
                logger.info("Spotify клиент инициализирован успешно")
            except Exception as e:
                logger.error(f"Ошибка инициализации Spotify клиента: {e}")
                self._enabled = False
        else:
            logger.warning("Spotify credentials не указаны, Spotify интеграция отключена")
    
    @property
    def is_enabled(self) -> bool:
        """Проверяет, включена ли интеграция со Spotify"""
        return self._enabled
    
    def is_spotify_url(self, url: str) -> bool:
        """Проверяет, является ли URL ссылкой на Spotify"""
        return bool(
            self.SPOTIFY_TRACK_REGEX.match(url) or
            self.SPOTIFY_ALBUM_REGEX.match(url) or
            self.SPOTIFY_PLAYLIST_REGEX.match(url)
        )
    
    def get_spotify_type(self, url: str) -> Optional[str]:
        """
        Определяет тип Spotify ресурса.
        
        Returns:
            'track', 'album', 'playlist' или None
        """
        if self.SPOTIFY_TRACK_REGEX.match(url):
            return 'track'
        elif self.SPOTIFY_ALBUM_REGEX.match(url):
            return 'album'
        elif self.SPOTIFY_PLAYLIST_REGEX.match(url):
            return 'playlist'
        return None
    
    def _extract_spotify_id(self, url: str) -> Optional[Tuple[str, str]]:
        """
        Извлекает ID и тип ресурса из Spotify URL/URI.
        
        Returns:
            Кортеж (type, id) или None
        """
        for regex, type_name in [
            (self.SPOTIFY_TRACK_REGEX, 'track'),
            (self.SPOTIFY_ALBUM_REGEX, 'album'),
            (self.SPOTIFY_PLAYLIST_REGEX, 'playlist')
        ]:
            match = regex.match(url)
            if match:
                return (type_name, match.group(2))
        return None
    
    async def get_track(self, url: str) -> Optional[Track]:
        """
        Получает трек по Spotify URL и находит его на YouTube.
        
        Args:
            url: Spotify URL или URI трека
            
        Returns:
            Track объект или None
        """
        if not self._enabled:
            logger.warning("Spotify не включен")
            return None
        
        extracted = self._extract_spotify_id(url)
        if not extracted or extracted[0] != 'track':
            return None
        
        track_id = extracted[1]
        
        try:
            loop = asyncio.get_event_loop()
            track_data = await loop.run_in_executor(
                self._executor,
                lambda: self._spotify.track(track_id)
            )
            
            if not track_data:
                return None
            
            # Формируем поисковый запрос для YouTube
            search_query = self._build_search_query(track_data)
            
            # Ищем на YouTube
            youtube_tracks = await self._youtube.search(search_query, max_results=1)
            
            if not youtube_tracks:
                logger.warning(f"Трек не найден на YouTube: {search_query}")
                return None
            
            track = youtube_tracks[0]
            
            # Обновляем метаданные из Spotify
            track.title = track_data['name']
            track.artist = ', '.join(a['name'] for a in track_data['artists'])
            track.album = track_data['album']['name']
            track.source = TrackSource.SPOTIFY
            
            # Используем обложку из Spotify если есть
            if track_data['album']['images']:
                track.thumbnail = track_data['album']['images'][0]['url']
            
            return track
            
        except Exception as e:
            logger.error(f"Ошибка получения трека Spotify: {e}")
            return None
    
    async def get_album_tracks(self, url: str, max_tracks: int = 50) -> List[Track]:
        """
        Получает треки из альбома Spotify.
        
        Args:
            url: Spotify URL или URI альбома
            max_tracks: Максимальное количество треков
            
        Returns:
            Список Track объектов
        """
        if not self._enabled:
            return []
        
        extracted = self._extract_spotify_id(url)
        if not extracted or extracted[0] != 'album':
            return []
        
        album_id = extracted[1]
        
        try:
            loop = asyncio.get_event_loop()
            album_data = await loop.run_in_executor(
                self._executor,
                lambda: self._spotify.album(album_id)
            )
            
            if not album_data or 'tracks' not in album_data:
                return []
            
            tracks = []
            album_name = album_data['name']
            album_image = album_data['images'][0]['url'] if album_data['images'] else None
            
            items = album_data['tracks']['items'][:max_tracks]
            
            for item in items:
                search_query = self._build_search_query_from_item(item, album_name)
                youtube_tracks = await self._youtube.search(search_query, max_results=1)
                
                if youtube_tracks:
                    track = youtube_tracks[0]
                    track.title = item['name']
                    track.artist = ', '.join(a['name'] for a in item['artists'])
                    track.album = album_name
                    track.source = TrackSource.SPOTIFY
                    if album_image:
                        track.thumbnail = album_image
                    tracks.append(track)
            
            logger.info(f"Извлечено {len(tracks)} треков из альбома Spotify")
            return tracks
            
        except Exception as e:
            logger.error(f"Ошибка получения альбома Spotify: {e}")
            return []
    
    async def get_playlist_tracks(self, url: str, max_tracks: int = 50) -> List[Track]:
        """
        Получает треки из плейлиста Spotify.
        
        Args:
            url: Spotify URL или URI плейлиста
            max_tracks: Максимальное количество треков
            
        Returns:
            Список Track объектов
        """
        if not self._enabled:
            return []
        
        extracted = self._extract_spotify_id(url)
        if not extracted or extracted[0] != 'playlist':
            return []
        
        playlist_id = extracted[1]
        
        try:
            loop = asyncio.get_event_loop()
            playlist_data = await loop.run_in_executor(
                self._executor,
                lambda: self._spotify.playlist(playlist_id)
            )
            
            if not playlist_data or 'tracks' not in playlist_data:
                return []
            
            tracks = []
            items = playlist_data['tracks']['items'][:max_tracks]
            
            for item in items:
                if not item.get('track'):
                    continue
                
                track_data = item['track']
                search_query = self._build_search_query(track_data)
                youtube_tracks = await self._youtube.search(search_query, max_results=1)
                
                if youtube_tracks:
                    track = youtube_tracks[0]
                    track.title = track_data['name']
                    track.artist = ', '.join(a['name'] for a in track_data['artists'])
                    track.album = track_data['album']['name']
                    track.source = TrackSource.SPOTIFY
                    
                    if track_data['album']['images']:
                        track.thumbnail = track_data['album']['images'][0]['url']
                    
                    tracks.append(track)
            
            logger.info(f"Извлечено {len(tracks)} треков из плейлиста Spotify")
            return tracks
            
        except Exception as e:
            logger.error(f"Ошибка получения плейлиста Spotify: {e}")
            return []
    
    def _build_search_query(self, track_data: dict) -> str:
        """Формирует поисковый запрос для YouTube из данных трека Spotify"""
        artists = ', '.join(a['name'] for a in track_data.get('artists', []))
        title = track_data.get('name', '')
        return f"{artists} - {title}"
    
    def _build_search_query_from_item(self, item: dict, album_name: str = '') -> str:
        """Формирует поисковый запрос из элемента трека"""
        artists = ', '.join(a['name'] for a in item.get('artists', []))
        title = item.get('name', '')
        return f"{artists} - {title}"
    
    def __del__(self):
        """Освобождает ресурсы"""
        if hasattr(self, '_executor'):
            self._executor.shutdown(wait=False)

