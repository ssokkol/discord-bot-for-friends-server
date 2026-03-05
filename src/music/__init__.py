"""
Музыкальный модуль для Discord бота.
Содержит компоненты для воспроизведения музыки из YouTube и Spotify.
"""

from .models import Track, QueueItem
from .queue import TrackQueue
from .youtube import YouTubeExtractor
from .spotify import SpotifyClient
from .player import MusicPlayer
from .permissions import PermissionChecker

__all__ = [
    'Track',
    'QueueItem', 
    'TrackQueue',
    'YouTubeExtractor',
    'SpotifyClient',
    'MusicPlayer',
    'PermissionChecker'
]

