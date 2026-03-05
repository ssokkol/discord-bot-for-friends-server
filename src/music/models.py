"""
Модели данных для музыкального плеера.
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
from datetime import datetime


class TrackSource(Enum):
    """Источник трека"""
    YOUTUBE = "youtube"
    SPOTIFY = "spotify"
    SEARCH = "search"


class LoopMode(Enum):
    """Режим повтора воспроизведения"""
    NONE = "none"      # Без повтора
    TRACK = "track"    # Повтор текущего трека
    QUEUE = "queue"    # Повтор всей очереди


@dataclass
class Track:
    """Модель трека"""
    title: str
    url: str
    duration: int  # в секундах
    thumbnail: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    source: TrackSource = TrackSource.YOUTUBE
    stream_url: Optional[str] = None  # URL для воспроизведения (извлекается позже)
    
    @property
    def duration_formatted(self) -> str:
        """Возвращает длительность в формате MM:SS или HH:MM:SS"""
        hours, remainder = divmod(self.duration, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"
    
    @property
    def display_name(self) -> str:
        """Возвращает отображаемое имя трека"""
        # Возвращаем только название видео, без исполнителя/канала
        return self.title
    
    def to_dict(self) -> dict:
        """Конвертирует трек в словарь"""
        return {
            'title': self.title,
            'url': self.url,
            'duration': self.duration,
            'thumbnail': self.thumbnail,
            'artist': self.artist,
            'album': self.album,
            'source': self.source.value,
            'stream_url': self.stream_url
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Track':
        """Создает трек из словаря"""
        source = TrackSource(data.get('source', 'youtube'))
        return cls(
            title=data['title'],
            url=data['url'],
            duration=data.get('duration', 0),
            thumbnail=data.get('thumbnail'),
            artist=data.get('artist'),
            album=data.get('album'),
            source=source,
            stream_url=data.get('stream_url')
        )


@dataclass
class QueueItem:
    """Элемент очереди воспроизведения"""
    track: Track
    requester_id: int
    requester_name: str
    added_at: datetime = field(default_factory=datetime.now)
    position: int = 0
    
    def to_embed_field(self) -> dict:
        """Возвращает данные для embed поля"""
        return {
            'name': f"{self.position}. {self.track.display_name}",
            'value': f"⏱️ {self.track.duration_formatted} | Запросил: {self.requester_name}",
            'inline': False
        }


@dataclass
class GuildMusicState:
    """Состояние музыкального плеера для сервера"""
    guild_id: int
    current_track: Optional[QueueItem] = None
    is_playing: bool = False
    is_paused: bool = False
    volume: int = 50
    loop_mode: LoopMode = LoopMode.NONE
    last_activity: datetime = field(default_factory=datetime.now)
    channel_owner_id: Optional[int] = None  # ID пользователя, который первым вызвал бота
    
    def update_activity(self):
        """Обновляет время последней активности"""
        self.last_activity = datetime.now()

