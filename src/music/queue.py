"""
Система очереди треков для музыкального плеера.
"""

import logging
from typing import Optional, List, Tuple
from collections import deque
from datetime import datetime

from .models import Track, QueueItem

logger = logging.getLogger(__name__)


class TrackQueue:
    """Очередь воспроизведения треков"""
    
    def __init__(self, max_size: int = 100):
        """
        Инициализация очереди.
        
        Args:
            max_size: Максимальный размер очереди
        """
        self._queue: deque[QueueItem] = deque()
        self._max_size = max_size
        self._current: Optional[QueueItem] = None
        self._history: List[QueueItem] = []
        self._history_limit = 10
    
    @property
    def current(self) -> Optional[QueueItem]:
        """Текущий воспроизводимый трек"""
        return self._current
    
    @current.setter
    def current(self, item: Optional[QueueItem]):
        """Устанавливает текущий трек"""
        if self._current and len(self._history) < self._history_limit:
            self._history.append(self._current)
        self._current = item
    
    @property
    def size(self) -> int:
        """Количество треков в очереди (без текущего)"""
        return len(self._queue)
    
    @property
    def is_empty(self) -> bool:
        """Проверяет, пуста ли очередь"""
        return len(self._queue) == 0
    
    @property
    def is_full(self) -> bool:
        """Проверяет, заполнена ли очередь"""
        return len(self._queue) >= self._max_size
    
    @property
    def total_duration(self) -> int:
        """Общая длительность очереди в секундах"""
        total = sum(item.track.duration for item in self._queue)
        if self._current:
            total += self._current.track.duration
        return total
    
    @property
    def total_duration_formatted(self) -> str:
        """Общая длительность в формате HH:MM:SS"""
        total = self.total_duration
        hours, remainder = divmod(total, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if hours > 0:
            return f"{hours}ч {minutes}м {seconds}с"
        elif minutes > 0:
            return f"{minutes}м {seconds}с"
        return f"{seconds}с"
    
    def add(
        self, 
        track: Track, 
        requester_id: int, 
        requester_name: str
    ) -> Optional[QueueItem]:
        """
        Добавляет трек в очередь.
        
        Args:
            track: Трек для добавления
            requester_id: ID пользователя, запросившего трек
            requester_name: Имя пользователя
            
        Returns:
            QueueItem или None если очередь заполнена
        """
        if self.is_full:
            logger.warning("Очередь заполнена")
            return None
        
        position = len(self._queue) + 1
        if self._current:
            position += 1
        
        item = QueueItem(
            track=track,
            requester_id=requester_id,
            requester_name=requester_name,
            position=position
        )
        
        self._queue.append(item)
        logger.debug(f"Трек добавлен в очередь: {track.display_name} (позиция {position})")
        
        return item
    
    def add_multiple(
        self, 
        tracks: List[Track], 
        requester_id: int, 
        requester_name: str
    ) -> List[QueueItem]:
        """
        Добавляет несколько треков в очередь.
        
        Args:
            tracks: Список треков
            requester_id: ID пользователя
            requester_name: Имя пользователя
            
        Returns:
            Список добавленных QueueItem
        """
        added = []
        for track in tracks:
            if self.is_full:
                break
            item = self.add(track, requester_id, requester_name)
            if item:
                added.append(item)
        return added
    
    def get_next(self) -> Optional[QueueItem]:
        """
        Получает следующий трек из очереди.
        
        Returns:
            Следующий QueueItem или None
        """
        if self.is_empty:
            return None
        
        item = self._queue.popleft()
        self._update_positions()
        
        return item
    
    def peek_next(self) -> Optional[QueueItem]:
        """
        Просматривает следующий трек без удаления из очереди.
        
        Returns:
            Следующий QueueItem или None
        """
        if self.is_empty:
            return None
        return self._queue[0]
    
    def remove_at(self, position: int) -> Optional[QueueItem]:
        """
        Удаляет трек по позиции.
        
        Args:
            position: Позиция в очереди (1-based)
            
        Returns:
            Удаленный QueueItem или None
        """
        # Позиция 1 - это текущий трек, позиция 2 - первый в очереди
        queue_index = position - 2 if self._current else position - 1
        
        if queue_index < 0 or queue_index >= len(self._queue):
            return None
        
        # Конвертируем deque в list для удаления по индексу
        queue_list = list(self._queue)
        removed = queue_list.pop(queue_index)
        self._queue = deque(queue_list)
        
        self._update_positions()
        return removed
    
    def clear(self):
        """Очищает очередь"""
        self._queue.clear()
        self._current = None
        logger.debug("Очередь очищена")
    
    def shuffle(self):
        """Перемешивает очередь"""
        import random
        queue_list = list(self._queue)
        random.shuffle(queue_list)
        self._queue = deque(queue_list)
        self._update_positions()
        logger.debug("Очередь перемешана")
    
    def get_page(self, page: int = 1, per_page: int = 10) -> Tuple[List[QueueItem], int, int]:
        """
        Получает страницу очереди для отображения.
        
        Args:
            page: Номер страницы (1-based)
            per_page: Количество треков на страницу
            
        Returns:
            Кортеж (список треков, номер страницы, всего страниц)
        """
        total_items = len(self._queue)
        total_pages = max(1, (total_items + per_page - 1) // per_page)
        
        page = max(1, min(page, total_pages))
        
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        
        items = list(self._queue)[start_idx:end_idx]
        
        return (items, page, total_pages)
    
    def get_all(self) -> List[QueueItem]:
        """Возвращает все треки в очереди"""
        return list(self._queue)
    
    def _update_positions(self):
        """Обновляет позиции всех треков в очереди"""
        start_pos = 2 if self._current else 1
        for i, item in enumerate(self._queue):
            item.position = start_pos + i
    
    def to_embed_data(self, page: int = 1, per_page: int = 10) -> dict:
        """
        Формирует данные для embed сообщения.
        
        Args:
            page: Номер страницы
            per_page: Треков на страницу
            
        Returns:
            Словарь с данными для embed
        """
        items, current_page, total_pages = self.get_page(page, per_page)
        
        data = {
            'current': None,
            'queue_items': [],
            'total_tracks': self.size,
            'total_duration': self.total_duration_formatted,
            'current_page': current_page,
            'total_pages': total_pages
        }
        
        if self._current:
            data['current'] = {
                'title': self._current.track.display_name,
                'duration': self._current.track.duration_formatted,
                'thumbnail': self._current.track.thumbnail,
                'requester': self._current.requester_name
            }
        
        for item in items:
            data['queue_items'].append({
                'position': item.position,
                'title': item.track.display_name,
                'duration': item.track.duration_formatted,
                'requester': item.requester_name
            })
        
        return data

