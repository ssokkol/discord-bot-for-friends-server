"""
Система проверки прав доступа для музыкального плеера.
"""

import logging
from typing import Optional, Tuple
from dataclasses import dataclass
from enum import IntEnum

import discord

logger = logging.getLogger(__name__)


class PermissionLevel(IntEnum):
    """Уровни прав доступа"""
    USER = 0
    MODERATOR = 1
    ADMIN = 2
    MAIN_ADMIN = 3


@dataclass
class PermissionResult:
    """Результат проверки прав"""
    allowed: bool
    reason: str = ""
    level: PermissionLevel = PermissionLevel.USER


class PermissionChecker:
    """Проверка прав доступа к музыкальным командам"""
    
    def __init__(
        self, 
        main_admin_id: str,
        admin_role_lvl0: int = 0,
        admin_role_lvl1: int = 0,
        admin_role_lvl2: int = 0
    ):
        """
        Инициализация проверки прав.
        
        Args:
            main_admin_id: ID главного администратора
            admin_role_lvl0: ID роли полного доступа (уровень 0)
            admin_role_lvl1: ID роли полного доступа (уровень 1)
            admin_role_lvl2: ID роли ограниченного доступа (уровень 2)
        """
        self._main_admin_id = int(main_admin_id) if main_admin_id else 0
        self._admin_roles = {
            admin_role_lvl0: PermissionLevel.ADMIN,
            admin_role_lvl1: PermissionLevel.ADMIN,
            admin_role_lvl2: PermissionLevel.MODERATOR
        }
        # Удаляем нулевые значения
        self._admin_roles = {k: v for k, v in self._admin_roles.items() if k}
    
    def get_user_permission_level(self, member: discord.Member) -> PermissionLevel:
        """
        Определяет уровень прав пользователя.
        
        Args:
            member: Участник сервера
            
        Returns:
            PermissionLevel пользователя
        """
        # Главный администратор
        if member.id == self._main_admin_id:
            return PermissionLevel.MAIN_ADMIN
        
        # Проверяем роли
        member_role_ids = {role.id for role in member.roles}
        
        max_level = PermissionLevel.USER
        for role_id, level in self._admin_roles.items():
            if role_id in member_role_ids and level > max_level:
                max_level = level
        
        return max_level
    
    def can_use_music_commands(self, member: discord.Member) -> PermissionResult:
        """
        Проверяет, может ли пользователь использовать музыкальные команды.
        
        Args:
            member: Участник сервера
            
        Returns:
            PermissionResult
        """
        # Все пользователи могут использовать базовые команды
        level = self.get_user_permission_level(member)
        return PermissionResult(
            allowed=True,
            reason="",
            level=level
        )
    
    def can_move_bot(
        self, 
        requester: discord.Member,
        current_channel: Optional[discord.VoiceChannel],
        target_channel: discord.VoiceChannel,
        channel_owner_id: Optional[int] = None
    ) -> PermissionResult:
        """
        Проверяет, может ли пользователь переместить бота в другой канал.
        
        Args:
            requester: Пользователь, запросивший перемещение
            current_channel: Текущий голосовой канал бота (или None)
            target_channel: Целевой голосовой канал
            channel_owner_id: ID пользователя, который первым вызвал бота
            
        Returns:
            PermissionResult
        """
        requester_level = self.get_user_permission_level(requester)
        
        # Бот не подключен - разрешаем
        if current_channel is None:
            return PermissionResult(
                allowed=True,
                reason="Бот свободен",
                level=requester_level
            )
        
        # Тот же канал - разрешаем
        if current_channel.id == target_channel.id:
            return PermissionResult(
                allowed=True,
                reason="Бот уже в этом канале",
                level=requester_level
            )
        
        # Главный админ может всегда
        if requester_level == PermissionLevel.MAIN_ADMIN:
            logger.info(f"Главный админ {requester.name} перемещает бота")
            return PermissionResult(
                allowed=True,
                reason="Главный администратор",
                level=requester_level
            )
        
        # Если нет владельца канала - разрешаем
        if channel_owner_id is None:
            return PermissionResult(
                allowed=True,
                reason="Нет владельца",
                level=requester_level
            )
        
        # Если запрашивающий - владелец - разрешаем
        if requester.id == channel_owner_id:
            return PermissionResult(
                allowed=True,
                reason="Владелец сессии",
                level=requester_level
            )
        
        # Сравниваем уровни прав
        # Находим владельца текущего канала
        owner_member = current_channel.guild.get_member(channel_owner_id)
        if owner_member:
            owner_level = self.get_user_permission_level(owner_member)
            
            if requester_level > owner_level:
                logger.info(
                    f"{requester.name} (уровень {requester_level.name}) "
                    f"перемещает бота от {owner_member.name} (уровень {owner_level.name})"
                )
                return PermissionResult(
                    allowed=True,
                    reason="Более высокий уровень прав",
                    level=requester_level
                )
        
        # Проверяем, есть ли кто-то в текущем канале
        if len(current_channel.members) <= 1:  # Только бот
            return PermissionResult(
                allowed=True,
                reason="Канал пуст",
                level=requester_level
            )
        
        return PermissionResult(
            allowed=False,
            reason="Бот уже используется в другом канале. "
                   "Дождитесь завершения или попросите пользователя с более высокими правами.",
            level=requester_level
        )
    
    def can_skip(
        self, 
        member: discord.Member, 
        track_requester_id: int
    ) -> PermissionResult:
        """
        Проверяет, может ли пользователь пропустить трек.
        
        Args:
            member: Участник, пытающийся пропустить
            track_requester_id: ID пользователя, запросившего трек
            
        Returns:
            PermissionResult
        """
        level = self.get_user_permission_level(member)
        
        # Пользователь может пропустить свой трек
        if member.id == track_requester_id:
            return PermissionResult(
                allowed=True,
                reason="Владелец трека",
                level=level
            )
        
        # Модераторы и выше могут пропускать любые треки
        if level >= PermissionLevel.MODERATOR:
            return PermissionResult(
                allowed=True,
                reason="Права модератора",
                level=level
            )
        
        return PermissionResult(
            allowed=False,
            reason="Вы можете пропускать только свои треки",
            level=level
        )
    
    def can_stop(self, member: discord.Member) -> PermissionResult:
        """
        Проверяет, может ли пользователь остановить воспроизведение.
        
        Args:
            member: Участник сервера
            
        Returns:
            PermissionResult
        """
        level = self.get_user_permission_level(member)
        
        # Модераторы и выше могут остановить
        if level >= PermissionLevel.MODERATOR:
            return PermissionResult(
                allowed=True,
                reason="Права модератора",
                level=level
            )
        
        # Обычные пользователи тоже могут (если они одни в канале - это проверяется в команде)
        return PermissionResult(
            allowed=True,
            reason="",
            level=level
        )
    
    def can_clear_queue(self, member: discord.Member) -> PermissionResult:
        """
        Проверяет, может ли пользователь очистить очередь.
        
        Args:
            member: Участник сервера
            
        Returns:
            PermissionResult
        """
        level = self.get_user_permission_level(member)
        
        if level >= PermissionLevel.MODERATOR:
            return PermissionResult(
                allowed=True,
                reason="Права модератора",
                level=level
            )
        
        return PermissionResult(
            allowed=False,
            reason="Недостаточно прав для очистки очереди",
            level=level
        )

