"""
Музыкальный плеер для Discord бота.
"""

import asyncio
import logging
from typing import Optional, Dict, Callable, Any
from datetime import datetime, timedelta

import discord
from discord.ext import tasks

from .models import Track, QueueItem, GuildMusicState, LoopMode
from .queue import TrackQueue
from .youtube import YouTubeExtractor, FFMPEG_OPTIONS

logger = logging.getLogger(__name__)


class MusicPlayer:
    """Основной класс музыкального плеера"""
    
    def __init__(
        self,
        youtube_extractor: YouTubeExtractor,
        inactivity_timeout: int = 300,
        max_queue_size: int = 100,
        default_volume: int = 50
    ):
        """
        Инициализация плеера.
        
        Args:
            youtube_extractor: Экземпляр YouTubeExtractor
            inactivity_timeout: Таймаут бездействия в секундах
            max_queue_size: Максимальный размер очереди
            default_volume: Громкость по умолчанию (0-100)
        """
        self._youtube = youtube_extractor
        self._inactivity_timeout = inactivity_timeout
        self._max_queue_size = max_queue_size
        self._default_volume = default_volume
        
        # Состояние плеера для каждого сервера
        self._states: Dict[int, GuildMusicState] = {}
        self._queues: Dict[int, TrackQueue] = {}
        self._voice_clients: Dict[int, discord.VoiceClient] = {}
        
        # Предзагруженные треки
        self._preloaded: Dict[int, Optional[str]] = {}
        
        # Callbacks
        self._on_track_start: Optional[Callable] = None
        self._on_track_end: Optional[Callable] = None
        self._on_queue_empty: Optional[Callable] = None
        self._on_error: Optional[Callable] = None
        
        # Счетчики retry
        self._retry_counts: Dict[int, int] = {}
        self._max_retries = 3
        
        # Event loop для корректной работы callback'ов
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
    def get_state(self, guild_id: int) -> GuildMusicState:
        """Получает или создает состояние для сервера"""
        if guild_id not in self._states:
            self._states[guild_id] = GuildMusicState(guild_id=guild_id)
        return self._states[guild_id]
    
    def get_queue(self, guild_id: int) -> TrackQueue:
        """Получает или создает очередь для сервера"""
        if guild_id not in self._queues:
            self._queues[guild_id] = TrackQueue(max_size=self._max_queue_size)
        return self._queues[guild_id]
    
    def get_voice_client(self, guild_id: int) -> Optional[discord.VoiceClient]:
        """Получает VoiceClient для сервера"""
        return self._voice_clients.get(guild_id)
    
    def is_playing(self, guild_id: int) -> bool:
        """Проверяет, играет ли музыка на сервере"""
        state = self.get_state(guild_id)
        return state.is_playing and not state.is_paused
    
    def is_connected(self, guild_id: int) -> bool:
        """Проверяет, подключен ли бот к голосовому каналу"""
        vc = self.get_voice_client(guild_id)
        return vc is not None and vc.is_connected()
    
    async def connect(
        self, 
        channel: discord.VoiceChannel,
        requester_id: int
    ) -> Optional[discord.VoiceClient]:
        """
        Подключается к голосовому каналу.
        
        Args:
            channel: Голосовой канал
            requester_id: ID пользователя, запросившего подключение
            
        Returns:
            VoiceClient или None при ошибке
        """
        guild_id = channel.guild.id
        
        try:
            # Если уже подключены к этому каналу
            if self.is_connected(guild_id):
                vc = self.get_voice_client(guild_id)
                if vc.channel.id == channel.id:
                    return vc
                # Переподключаемся к новому каналу
                await vc.move_to(channel)
                return vc
            
            # Подключаемся к каналу
            vc = await channel.connect(timeout=10.0, reconnect=True)
            self._voice_clients[guild_id] = vc
            
            # Обновляем состояние
            state = self.get_state(guild_id)
            state.channel_owner_id = requester_id
            state.update_activity()
            
            logger.info(f"Подключен к каналу {channel.name} на сервере {channel.guild.name}")
            return vc
            
        except asyncio.TimeoutError:
            logger.error(f"Таймаут подключения к каналу {channel.name}")
            return None
        except Exception as e:
            logger.error(f"Ошибка подключения к каналу: {e}")
            return None
    
    async def disconnect(self, guild_id: int):
        """Отключается от голосового канала"""
        vc = self.get_voice_client(guild_id)
        
        if vc:
            try:
                if vc.is_playing():
                    vc.stop()
                await vc.disconnect(force=True)
            except Exception as e:
                logger.error(f"Ошибка отключения: {e}")
            finally:
                if guild_id in self._voice_clients:
                    del self._voice_clients[guild_id]
        
        # Очищаем состояние
        if guild_id in self._states:
            self._states[guild_id] = GuildMusicState(guild_id=guild_id)
        
        # Очищаем очередь
        queue = self.get_queue(guild_id)
        queue.clear()
        
        # Очищаем предзагрузку
        if guild_id in self._preloaded:
            del self._preloaded[guild_id]
        
        logger.info(f"Отключен от сервера {guild_id}")
    
    async def play(
        self, 
        guild_id: int, 
        track: Track,
        requester_id: int,
        requester_name: str
    ) -> Optional[QueueItem]:
        """
        Воспроизводит или добавляет трек в очередь.
        
        Args:
            guild_id: ID сервера
            track: Трек для воспроизведения
            requester_id: ID пользователя
            requester_name: Имя пользователя
            
        Returns:
            QueueItem или None
        """
        queue = self.get_queue(guild_id)
        state = self.get_state(guild_id)
        
        # Добавляем в очередь
        item = queue.add(track, requester_id, requester_name)
        
        if not item:
            logger.warning("Не удалось добавить трек в очередь")
            return None
        
        # Если не играет - запускаем
        if not state.is_playing:
            await self._play_next(guild_id)
        else:
            # Предзагружаем следующий трек
            await self._preload_next(guild_id)
        
        state.update_activity()
        return item
    
    async def play_multiple(
        self,
        guild_id: int,
        tracks: list[Track],
        requester_id: int,
        requester_name: str
    ) -> list[QueueItem]:
        """
        Добавляет несколько треков в очередь.
        
        Args:
            guild_id: ID сервера
            tracks: Список треков
            requester_id: ID пользователя
            requester_name: Имя пользователя
            
        Returns:
            Список добавленных QueueItem
        """
        queue = self.get_queue(guild_id)
        state = self.get_state(guild_id)
        
        items = queue.add_multiple(tracks, requester_id, requester_name)
        
        # Если не играет - запускаем
        if not state.is_playing and items:
            await self._play_next(guild_id)
        
        state.update_activity()
        return items
    
    async def skip(self, guild_id: int) -> Optional[QueueItem]:
        """
        Пропускает текущий трек.
        
        Args:
            guild_id: ID сервера
            
        Returns:
            Следующий QueueItem или None
        """
        vc = self.get_voice_client(guild_id)
        state = self.get_state(guild_id)
        queue = self.get_queue(guild_id)
        
        if not vc:
            return None
        
        # Останавливаем текущий трек (это вызовет _on_track_finished)
        if vc.is_playing():
            vc.stop()
        
        state.update_activity()
        
        # Возвращаем следующий трек из очереди
        return queue.peek_next()
    
    async def stop(self, guild_id: int):
        """
        Останавливает воспроизведение и очищает очередь.
        
        Args:
            guild_id: ID сервера
        """
        await self.disconnect(guild_id)
    
    def pause(self, guild_id: int) -> bool:
        """
        Приостанавливает воспроизведение.
        
        Args:
            guild_id: ID сервера
            
        Returns:
            True если пауза успешна
        """
        vc = self.get_voice_client(guild_id)
        state = self.get_state(guild_id)
        
        if vc and vc.is_playing():
            vc.pause()
            state.is_paused = True
            state.update_activity()
            return True
        return False
    
    def resume(self, guild_id: int) -> bool:
        """
        Возобновляет воспроизведение.
        
        Args:
            guild_id: ID сервера
            
        Returns:
            True если возобновление успешно
        """
        vc = self.get_voice_client(guild_id)
        state = self.get_state(guild_id)
        
        if vc and vc.is_paused():
            vc.resume()
            state.is_paused = False
            state.update_activity()
            return True
        return False
    
    def set_volume(self, guild_id: int, volume: int) -> bool:
        """
        Устанавливает громкость.
        
        Args:
            guild_id: ID сервера
            volume: Громкость (0-100)
            
        Returns:
            True если успешно
        """
        volume = max(0, min(100, volume))
        state = self.get_state(guild_id)
        state.volume = volume
        
        vc = self.get_voice_client(guild_id)
        if vc and vc.source:
            vc.source.volume = volume / 100
            return True
        return False
    
    def set_loop_mode(self, guild_id: int, mode: LoopMode) -> bool:
        """
        Устанавливает режим повтора.
        
        Args:
            guild_id: ID сервера
            mode: Режим повтора (LoopMode.NONE, LoopMode.TRACK, LoopMode.QUEUE)
            
        Returns:
            True если успешно
        """
        state = self.get_state(guild_id)
        state.loop_mode = mode
        logger.info(f"Режим повтора установлен: {mode.value} для сервера {guild_id}")
        return True
    
    def get_loop_mode(self, guild_id: int) -> LoopMode:
        """
        Получает текущий режим повтора.
        
        Args:
            guild_id: ID сервера
            
        Returns:
            Текущий режим повтора
        """
        state = self.get_state(guild_id)
        return state.loop_mode
    
    def clear_queue(self, guild_id: int) -> int:
        """
        Очищает очередь треков (оставляет текущий трек).
        
        Args:
            guild_id: ID сервера
            
        Returns:
            Количество удаленных треков
        """
        queue = self.get_queue(guild_id)
        cleared_count = len(queue._queue)
        queue._queue.clear()
        queue._update_positions()
        logger.info(f"Очередь очищена, удалено {cleared_count} треков")
        return cleared_count
    
    async def _play_track(self, guild_id: int, item: QueueItem):
        """Воспроизводит конкретный трек"""
        # Сохраняем ссылку на event loop для callback'а
        self._loop = asyncio.get_running_loop()
        
        state = self.get_state(guild_id)
        queue = self.get_queue(guild_id)
        vc = self.get_voice_client(guild_id)
        
        if not vc or not vc.is_connected():
            logger.warning("VoiceClient не подключен")
            state.is_playing = False
            return
        
        queue.current = item
        state.current_track = item
        
        # Получаем URL потока
        stream_url = await self._youtube.get_stream_url(item.track)
        
        if not stream_url:
            logger.error(f"Не удалось получить stream URL для {item.track.title}")
            if self._on_error:
                await self._on_error(guild_id, "Не удалось воспроизвести трек")
            return
        
        try:
            # Создаем аудио источник
            source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)
            source = discord.PCMVolumeTransformer(source, volume=state.volume / 100)
            
            # Воспроизводим
            vc.play(
                source,
                after=lambda e: asyncio.run_coroutine_threadsafe(
                    self._on_track_finished(guild_id, e),
                    self._loop
                )
            )
            
            state.is_playing = True
            state.is_paused = False
            state.update_activity()
            
            logger.info(f"Воспроизведение: {item.track.display_name}")
            
            if self._on_track_start:
                await self._on_track_start(guild_id, item)
            
            # Предзагружаем следующий трек
            await self._preload_next(guild_id)
            
        except Exception as e:
            logger.error(f"Ошибка воспроизведения: {e}")
            state.is_playing = False
            if self._on_error:
                await self._on_error(guild_id, str(e))
    
    async def _play_next(self, guild_id: int):
        """Воспроизводит следующий трек из очереди"""
        # Сохраняем ссылку на event loop для callback'а
        self._loop = asyncio.get_running_loop()
        
        queue = self.get_queue(guild_id)
        state = self.get_state(guild_id)
        vc = self.get_voice_client(guild_id)
        
        if not vc or not vc.is_connected():
            logger.warning("VoiceClient не подключен")
            state.is_playing = False
            return
        
        # Получаем следующий трек
        next_item = queue.get_next()
        
        if not next_item:
            logger.debug("Очередь пуста")
            state.is_playing = False
            state.current_track = None
            queue.current = None
            
            if self._on_queue_empty:
                await self._on_queue_empty(guild_id)
            return
        
        queue.current = next_item
        state.current_track = next_item
        
        # Получаем URL потока
        stream_url = self._preloaded.get(guild_id) or await self._youtube.get_stream_url(next_item.track)
        
        if not stream_url:
            logger.error(f"Не удалось получить stream URL для {next_item.track.title}")
            # Пробуем следующий трек
            if self._retry_counts.get(guild_id, 0) < self._max_retries:
                self._retry_counts[guild_id] = self._retry_counts.get(guild_id, 0) + 1
                await self._play_next(guild_id)
            else:
                self._retry_counts[guild_id] = 0
                if self._on_error:
                    await self._on_error(guild_id, "Не удалось воспроизвести трек")
            return
        
        self._retry_counts[guild_id] = 0
        
        try:
            # Создаем аудио источник
            source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)
            source = discord.PCMVolumeTransformer(source, volume=state.volume / 100)
            
            # Воспроизводим
            vc.play(
                source,
                after=lambda e: asyncio.run_coroutine_threadsafe(
                    self._on_track_finished(guild_id, e),
                    self._loop
                )
            )
            
            state.is_playing = True
            state.is_paused = False
            state.update_activity()
            
            logger.info(f"Воспроизведение: {next_item.track.display_name}")
            
            if self._on_track_start:
                await self._on_track_start(guild_id, next_item)
            
            # Предзагружаем следующий трек
            await self._preload_next(guild_id)
            
        except Exception as e:
            logger.error(f"Ошибка воспроизведения: {e}")
            state.is_playing = False
            if self._on_error:
                await self._on_error(guild_id, str(e))
    
    async def _on_track_finished(self, guild_id: int, error: Optional[Exception]):
        """Вызывается при завершении трека"""
        if error:
            logger.error(f"Ошибка воспроизведения: {error}")
        
        state = self.get_state(guild_id)
        queue = self.get_queue(guild_id)
        
        if self._on_track_end and state.current_track:
            await self._on_track_end(guild_id, state.current_track)
        
        # Обработка режимов повтора
        if state.loop_mode == LoopMode.TRACK and state.current_track:
            # Повтор текущего трека - воспроизводим его снова
            current = state.current_track
            logger.debug(f"Повтор трека: {current.track.title}")
            # Просто воспроизводим текущий трек снова
            await self._play_track(guild_id, current)
            return
        elif state.loop_mode == LoopMode.QUEUE and state.current_track:
            # Повтор очереди - возвращаем трек в конец очереди
            current = state.current_track
            queue._queue.append(
                QueueItem(
                    track=current.track,
                    requester_id=current.requester_id,
                    requester_name=current.requester_name,
                    position=len(queue._queue) + 2
                )
            )
            queue._update_positions()
            logger.debug(f"Трек {current.track.title} добавлен в конец очереди для повтора")
        
        # Воспроизводим следующий
        await self._play_next(guild_id)
    
    async def _preload_next(self, guild_id: int):
        """Предзагружает следующий трек"""
        queue = self.get_queue(guild_id)
        next_item = queue.peek_next()
        
        if next_item:
            stream_url = await self._youtube.get_stream_url(next_item.track)
            self._preloaded[guild_id] = stream_url
            logger.debug(f"Предзагружен: {next_item.track.title}")
        else:
            self._preloaded[guild_id] = None
    
    async def check_inactivity(self, guild_id: int) -> bool:
        """
        Проверяет бездействие и отключает если нужно.
        
        Args:
            guild_id: ID сервера
            
        Returns:
            True если был отключен из-за бездействия
        """
        state = self.get_state(guild_id)
        vc = self.get_voice_client(guild_id)
        
        if not vc or not vc.is_connected():
            return False
        
        # Проверяем, есть ли кто-то в канале кроме бота
        if vc.channel and len([m for m in vc.channel.members if not m.bot]) == 0:
            logger.info(f"Канал пуст, отключаюсь от {guild_id}")
            await self.disconnect(guild_id)
            return True
        
        # Проверяем таймаут бездействия
        if not state.is_playing:
            inactive_time = datetime.now() - state.last_activity
            if inactive_time > timedelta(seconds=self._inactivity_timeout):
                logger.info(f"Таймаут бездействия на сервере {guild_id}")
                await self.disconnect(guild_id)
                return True
        
        return False
    
    def set_on_track_start(self, callback: Callable):
        """Устанавливает callback при старте трека"""
        self._on_track_start = callback
    
    def set_on_track_end(self, callback: Callable):
        """Устанавливает callback при завершении трека"""
        self._on_track_end = callback
    
    def set_on_queue_empty(self, callback: Callable):
        """Устанавливает callback при опустошении очереди"""
        self._on_queue_empty = callback
    
    def set_on_error(self, callback: Callable):
        """Устанавливает callback при ошибке"""
        self._on_error = callback

