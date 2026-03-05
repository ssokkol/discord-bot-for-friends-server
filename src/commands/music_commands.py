"""
Музыкальные команды для Discord бота.
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
from typing import Optional

from .base_command import BaseCommand
from ..music import (
    MusicPlayer, 
    TrackQueue, 
    YouTubeExtractor, 
    SpotifyClient,
    PermissionChecker,
    Track,
    QueueItem
)
from ..music.models import LoopMode
from ..music.permissions import PermissionLevel

logger = logging.getLogger(__name__)


class QueuePaginationView(discord.ui.View):
    """View для пагинации очереди"""
    
    def __init__(self, music_commands: 'MusicCommands', guild_id: int, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.music_commands = music_commands
        self.guild_id = guild_id
        self.current_page = 1
    
    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 1:
            self.current_page -= 1
            embed = await self.music_commands._create_queue_embed(self.guild_id, self.current_page)
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        queue = self.music_commands.player.get_queue(self.guild_id)
        _, _, total_pages = queue.get_page(self.current_page)
        
        if self.current_page < total_pages:
            self.current_page += 1
            embed = await self.music_commands._create_queue_embed(self.guild_id, self.current_page)
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()


class MusicControlView(discord.ui.View):
    """View с кнопками управления воспроизведением"""
    
    def __init__(self, music_commands: 'MusicCommands', guild_id: int, timeout: float = None):
        super().__init__(timeout=timeout)
        self.music_commands = music_commands
        self.guild_id = guild_id
    
    @discord.ui.button(emoji="⏸️", style=discord.ButtonStyle.secondary)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = self.music_commands.player.get_state(self.guild_id)
        
        if state.is_paused:
            self.music_commands.player.resume(self.guild_id)
            button.emoji = "⏸️"
            await interaction.response.edit_message(view=self)
        else:
            self.music_commands.player.pause(self.guild_id)
            button.emoji = "▶️"
            await interaction.response.edit_message(view=self)
    
    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        queue = self.music_commands.player.get_queue(self.guild_id)
        current = queue.current
        
        # Проверяем права на пропуск
        if current:
            result = self.music_commands.permissions.can_skip(
                interaction.user, 
                current.requester_id
            )
            if not result.allowed:
                await interaction.response.send_message(result.reason, ephemeral=True)
                return
        
        await self.music_commands.player.skip(self.guild_id)
        await interaction.response.send_message("⏭️ Трек пропущен", ephemeral=True)
    
    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger)
    async def stop_playback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_commands.player.stop(self.guild_id)
        
        # Возвращаем активность по умолчанию
        try:
            activity = discord.Activity(
                type=discord.ActivityType.listening,
                name=self.music_commands.bot.config.BOT_ACTIVITY_NAME
            )
            await self.music_commands.bot.change_presence(
                activity=activity,
                status=discord.Status.do_not_disturb
            )
        except Exception as e:
            logger.error(f"Error restoring activity: {e}")

        await interaction.response.send_message("⏹️ Воспроизведение остановлено", ephemeral=True)
        self.stop()


class MusicCommands(BaseCommand):
    """Класс музыкальных команд"""
    
    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        
        # Инициализация компонентов
        self.youtube = YouTubeExtractor()
        self.spotify = SpotifyClient(
            client_id=bot.config.SPOTIFY_CLIENT_ID,
            client_secret=bot.config.SPOTIFY_CLIENT_SECRET,
            youtube_extractor=self.youtube
        )
        self.player = MusicPlayer(
            youtube_extractor=self.youtube,
            inactivity_timeout=bot.config.MUSIC_INACTIVITY_TIMEOUT,
            max_queue_size=bot.config.MUSIC_MAX_QUEUE_SIZE,
            default_volume=bot.config.MUSIC_DEFAULT_VOLUME
        )
        self.permissions = PermissionChecker(
            main_admin_id=bot.config.ADMIN_USER_ID,
            admin_role_lvl0=bot.config.ADMIN_ROLE_LVL0,
            admin_role_lvl1=bot.config.ADMIN_ROLE_LVL1,
            admin_role_lvl2=bot.config.ADMIN_ROLE_LVL2
        )
        
        # Устанавливаем callbacks
        self.player.set_on_track_start(self._on_track_start)
        self.player.set_on_queue_empty(self._on_queue_empty)
        self.player.set_on_error(self._on_error)
        
        # Запускаем проверку бездействия
        self._inactivity_check.start()
        
        # Храним каналы для уведомлений
        self._notification_channels: dict[int, int] = {}
    
    @tasks.loop(minutes=1)
    async def _inactivity_check(self):
        """Проверяет бездействие на всех серверах"""
        for guild_id in list(self.player._states.keys()):
            await self.player.check_inactivity(guild_id)
    
    @_inactivity_check.before_loop
    async def before_inactivity_check(self):
        await self.bot.wait_until_ready()
    
    def _check_channel_permission(self, interaction: discord.Interaction) -> tuple[bool, str]:
        """
        Проверяет, может ли пользователь использовать музыкальные команды в этом канале.
        
        Returns:
            Кортеж (разрешено, сообщение об ошибке)
        """
        # Админы и модераторы могут использовать везде
        level = self.permissions.get_user_permission_level(interaction.user)
        if level >= PermissionLevel.MODERATOR:
            return True, ""
        
        # Обычные пользователи - только в музыкальном канале
        music_channel_id = self.bot.config.MUSIC_CHANNEL_ID
        if music_channel_id and interaction.channel_id != music_channel_id:
            return False, f"❌ Музыкальные команды доступны только в <#{music_channel_id}>"
        
        return True, ""
    
    async def _on_track_start(self, guild_id: int, item: QueueItem):
        """Callback при старте трека"""
        # Меняем активность бота на текущий трек
        try:
            activity = discord.Activity(
                type=discord.ActivityType.listening,
                name=item.track.display_name[:128]  # Discord limit
            )
            await self.bot.change_presence(
                activity=activity,
                status=discord.Status.do_not_disturb
            )
        except Exception as e:
            logger.error(f"Ошибка смены активности: {e}")
        
        channel_id = self._notification_channels.get(guild_id)
        if not channel_id:
            return
        
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return
        
        embed = self._create_now_playing_embed(item)
        view = MusicControlView(self, guild_id)
        
        try:
            await channel.send(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления: {e}")
    
    async def _on_queue_empty(self, guild_id: int):
        """Callback при опустошении очереди"""
        # Возвращаем активность по умолчанию
        try:
            activity = discord.Activity(
                type=discord.ActivityType.listening,
                name=self.bot.config.BOT_ACTIVITY_NAME
            )
            await self.bot.change_presence(
                activity=activity,
                status=discord.Status.do_not_disturb
            )
        except Exception as e:
            logger.error(f"Ошибка смены активности: {e}")
        
        channel_id = self._notification_channels.get(guild_id)
        if not channel_id:
            return
        
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return
        
        embed = discord.Embed(
            title="📭 Очередь пуста",
            description="Добавьте треки командой `/play`",
            color=discord.Color.orange()
        )
        
        try:
            await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления: {e}")
    
    async def _on_error(self, guild_id: int, error: str):
        """Callback при ошибке"""
        channel_id = self._notification_channels.get(guild_id)
        if not channel_id:
            return
        
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return
        
        embed = discord.Embed(
            title="❌ Ошибка воспроизведения",
            description=error,
            color=discord.Color.red()
        )
        
        try:
            await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления: {e}")
    
    def _create_now_playing_embed(self, item: QueueItem) -> discord.Embed:
        """Создает embed для текущего трека"""
        embed = discord.Embed(
            title="🎵 Сейчас играет",
            color=discord.Color.green()
        )
        
        embed.add_field(
            name=item.track.display_name,
            value=f"⏱️ {item.track.duration_formatted}",
            inline=False
        )
        
        if item.track.thumbnail:
            embed.set_thumbnail(url=item.track.thumbnail)
        
        embed.set_footer(text=f"Запросил: {item.requester_name}")
        
        return embed
    
    async def _create_queue_embed(self, guild_id: int, page: int = 1) -> discord.Embed:
        """Создает embed для очереди"""
        queue = self.player.get_queue(guild_id)
        data = queue.to_embed_data(page=page, per_page=10)
        state = self.player.get_state(guild_id)
        
        # Получаем режим повтора
        loop_mode = state.loop_mode
        loop_text = ""
        if loop_mode == LoopMode.TRACK:
            loop_text = "🔂 Повтор трека"
        elif loop_mode == LoopMode.QUEUE:
            loop_text = "🔁 Повтор очереди"
        
        embed = discord.Embed(
            title="📜 Очередь воспроизведения",
            color=discord.Color.blue()
        )
        
        # Текущий трек
        if data['current']:
            current = data['current']
            current_text = f"**{current['title']}**\n⏱️ {current['duration']} | Запросил: {current['requester']}"
            if loop_mode == LoopMode.TRACK:
                current_text += "\n🔂 Повтор трека"
            embed.add_field(
                name="▶️ Сейчас играет",
                value=current_text,
                inline=False
            )
            if current['thumbnail']:
                embed.set_thumbnail(url=current['thumbnail'])
        
        # Треки в очереди
        if data['queue_items']:
            queue_text = ""
            for item in data['queue_items']:
                queue_text += f"`{item['position']}.` {item['title']} [{item['duration']}]\n"
            
            embed.add_field(
                name=f"📋 Далее ({data['total_tracks']} треков)",
                value=queue_text[:1024],  # Ограничение Discord
                inline=False
            )
        else:
            embed.add_field(
                name="📋 Очередь",
                value="Пусто",
                inline=False
            )
        
        footer_text = f"Страница {data['current_page']}/{data['total_pages']} | Общее время: {data['total_duration']}"
        if loop_text:
            footer_text += f" | {loop_text}"
        
        embed.set_footer(text=footer_text)
        
        return embed
    
    async def play(self, interaction: discord.Interaction, query: str):
        """Команда воспроизведения"""
        # Проверяем канал
        allowed, error_msg = self._check_channel_permission(interaction)
        if not allowed:
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        
        await interaction.response.defer()
        
        # Проверяем, что пользователь в голосовом канале
        if not interaction.user.voice:
            await interaction.followup.send(
                "❌ Вы должны быть в голосовом канале",
                ephemeral=True
            )
            return
        
        target_channel = interaction.user.voice.channel
        guild_id = interaction.guild_id
        
        # Проверяем права на перемещение бота
        current_vc = self.player.get_voice_client(guild_id)
        current_channel = current_vc.channel if current_vc and current_vc.is_connected() else None
        state = self.player.get_state(guild_id)
        
        permission = self.permissions.can_move_bot(
            interaction.user,
            current_channel,
            target_channel,
            state.channel_owner_id
        )
        
        if not permission.allowed:
            await interaction.followup.send(
                f"❌ {permission.reason}",
                ephemeral=True
            )
            return
        
        # Подключаемся к каналу
        vc = await self.player.connect(target_channel, interaction.user.id)
        if not vc:
            await interaction.followup.send(
                "❌ Не удалось подключиться к голосовому каналу",
                ephemeral=True
            )
            return
        
        # Сохраняем канал для уведомлений
        self._notification_channels[guild_id] = interaction.channel_id
        
        # Определяем тип запроса и извлекаем треки
        tracks = []
        
        # Проверяем Spotify
        if self.spotify.is_enabled and self.spotify.is_spotify_url(query):
            spotify_type = self.spotify.get_spotify_type(query)
            
            await interaction.followup.send(
                f"🔍 Обработка Spotify {spotify_type}...",
                ephemeral=True
            )
            
            if spotify_type == 'track':
                track = await self.spotify.get_track(query)
                if track:
                    tracks = [track]
            elif spotify_type == 'album':
                tracks = await self.spotify.get_album_tracks(query)
            elif spotify_type == 'playlist':
                tracks = await self.spotify.get_playlist_tracks(query)
        
        # Проверяем YouTube
        elif self.youtube.is_youtube_url(query):
            if self.youtube.is_playlist_url(query):
                await interaction.followup.send(
                    "🔍 Загрузка плейлиста...",
                    ephemeral=True
                )
                tracks = await self.youtube.extract_playlist(query)
            else:
                track = await self.youtube.extract_track(query)
                if track:
                    tracks = [track]
        
        # Поиск по запросу
        else:
            track = await self.youtube.extract_track(query)
            if track:
                tracks = [track]
        
        if not tracks:
            await interaction.followup.send(
                "❌ Ничего не найдено по запросу",
                ephemeral=True
            )
            return
        
        # Добавляем треки
        if len(tracks) == 1:
            item = await self.player.play(
                guild_id,
                tracks[0],
                interaction.user.id,
                interaction.user.display_name
            )
            
            if item:
                queue = self.player.get_queue(guild_id)
                if queue.current and queue.current.track.url == tracks[0].url:
                    # Трек играет сейчас
                    embed = self._create_now_playing_embed(item)
                    await interaction.followup.send(embed=embed)
                else:
                    # Трек добавлен в очередь
                    embed = discord.Embed(
                        title="✅ Добавлено в очередь",
                        description=f"**{tracks[0].display_name}**",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="Позиция", value=str(item.position), inline=True)
                    embed.add_field(name="Длительность", value=tracks[0].duration_formatted, inline=True)
                    
                    if tracks[0].thumbnail:
                        embed.set_thumbnail(url=tracks[0].thumbnail)
                    
                    await interaction.followup.send(embed=embed)
        else:
            # Несколько треков
            items = await self.player.play_multiple(
                guild_id,
                tracks,
                interaction.user.id,
                interaction.user.display_name
            )
            
            embed = discord.Embed(
                title="✅ Добавлено в очередь",
                description=f"Добавлено **{len(items)}** треков",
                color=discord.Color.green()
            )
            
            if items:
                first_tracks = items[:5]
                tracks_text = "\n".join(
                    f"`{i.position}.` {i.track.display_name}" 
                    for i in first_tracks
                )
                if len(items) > 5:
                    tracks_text += f"\n... и еще {len(items) - 5}"
                
                embed.add_field(name="Треки", value=tracks_text, inline=False)
            
            await interaction.followup.send(embed=embed)
    
    async def skip(self, interaction: discord.Interaction):
        """Команда пропуска трека"""
        # Проверяем канал
        allowed, error_msg = self._check_channel_permission(interaction)
        if not allowed:
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        
        guild_id = interaction.guild_id
        
        if not self.player.is_connected(guild_id):
            await interaction.response.send_message(
                "❌ Бот не воспроизводит музыку",
                ephemeral=True
            )
            return
        
        queue = self.player.get_queue(guild_id)
        current = queue.current
        
        # Проверяем права
        if current:
            result = self.permissions.can_skip(interaction.user, current.requester_id)
            if not result.allowed:
                await interaction.response.send_message(
                    f"❌ {result.reason}",
                    ephemeral=True
                )
                return
        
        next_item = await self.player.skip(guild_id)
        
        if next_item:
            embed = discord.Embed(
                title="⏭️ Трек пропущен",
                description=f"Следующий: **{next_item.track.display_name}**",
                color=discord.Color.blue()
            )
            if next_item.track.thumbnail:
                embed.set_thumbnail(url=next_item.track.thumbnail)
        else:
            embed = discord.Embed(
                title="⏭️ Трек пропущен",
                description="Очередь пуста",
                color=discord.Color.orange()
            )
        
        await interaction.response.send_message(embed=embed)
    
    async def show_queue(self, interaction: discord.Interaction):
        """Команда отображения очереди"""
        # Проверяем канал
        allowed, error_msg = self._check_channel_permission(interaction)
        if not allowed:
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        
        guild_id = interaction.guild_id
        
        if not self.player.is_connected(guild_id):
            await interaction.response.send_message(
                "❌ Очередь пуста",
                ephemeral=True
            )
            return
        
        embed = await self._create_queue_embed(guild_id)
        view = QueuePaginationView(self, guild_id)
        
        await interaction.response.send_message(embed=embed, view=view)
    
    async def stop(self, interaction: discord.Interaction):
        """Команда остановки воспроизведения"""
        # Проверяем канал
        allowed, error_msg = self._check_channel_permission(interaction)
        if not allowed:
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        
        guild_id = interaction.guild_id
        
        if not self.player.is_connected(guild_id):
            await interaction.response.send_message(
                "❌ Бот не воспроизводит музыку",
                ephemeral=True
            )
            return
        
        await self.player.stop(guild_id)
        
        # Очищаем канал уведомлений
        if guild_id in self._notification_channels:
            del self._notification_channels[guild_id]
        
        # Возвращаем активность по умолчанию
        try:
            activity = discord.Activity(
                type=discord.ActivityType.listening,
                name=self.bot.config.BOT_ACTIVITY_NAME
            )
            await self.bot.change_presence(
                activity=activity,
                status=discord.Status.do_not_disturb
            )
        except Exception as e:
            logger.error(f"Ошибка смены активности: {e}")
        
        embed = discord.Embed(
            title="⏹️ Воспроизведение остановлено",
            description="Очередь очищена, бот отключен",
            color=discord.Color.red()
        )
        
        await interaction.response.send_message(embed=embed)
    
    async def pause(self, interaction: discord.Interaction):
        """Команда паузы"""
        # Проверяем канал
        allowed, error_msg = self._check_channel_permission(interaction)
        if not allowed:
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        
        guild_id = interaction.guild_id
        state = self.player.get_state(guild_id)
        
        if state.is_paused:
            if self.player.resume(guild_id):
                await interaction.response.send_message("▶️ Воспроизведение возобновлено")
            else:
                await interaction.response.send_message("❌ Не удалось возобновить", ephemeral=True)
        else:
            if self.player.pause(guild_id):
                await interaction.response.send_message("⏸️ Пауза")
            else:
                await interaction.response.send_message("❌ Не удалось поставить на паузу", ephemeral=True)
    
    async def loop(self, interaction: discord.Interaction):
        """Команда переключения режима повтора"""
        # Проверяем канал
        allowed, error_msg = self._check_channel_permission(interaction)
        if not allowed:
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        
        guild_id = interaction.guild_id
        
        if not self.player.is_connected(guild_id):
            await interaction.response.send_message(
                "❌ Бот не воспроизводит музыку",
                ephemeral=True
            )
            return
        
        current_mode = self.player.get_loop_mode(guild_id)
        
        # Переключаем режим: NONE -> TRACK -> QUEUE -> NONE
        if current_mode == LoopMode.NONE:
            new_mode = LoopMode.TRACK
            mode_text = "🔂 Повтор трека"
        elif current_mode == LoopMode.TRACK:
            new_mode = LoopMode.QUEUE
            mode_text = "🔁 Повтор очереди"
        else:  # QUEUE
            new_mode = LoopMode.NONE
            mode_text = "▶️ Без повтора"
        
        self.player.set_loop_mode(guild_id, new_mode)
        
        embed = discord.Embed(
            title="🔄 Режим повтора изменен",
            description=mode_text,
            color=discord.Color.blue()
        )
        
        await interaction.response.send_message(embed=embed)
    
    async def clear(self, interaction: discord.Interaction):
        """Команда очистки очереди"""
        # Проверяем канал
        allowed, error_msg = self._check_channel_permission(interaction)
        if not allowed:
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        
        guild_id = interaction.guild_id
        
        if not self.player.is_connected(guild_id):
            await interaction.response.send_message(
                "❌ Бот не воспроизводит музыку",
                ephemeral=True
            )
            return
        
        # Проверяем права на очистку очереди
        result = self.permissions.can_clear_queue(interaction.user)
        if not result.allowed:
            await interaction.response.send_message(
                f"❌ {result.reason}",
                ephemeral=True
            )
            return
        
        cleared_count = self.player.clear_queue(guild_id)
        
        embed = discord.Embed(
            title="🗑️ Очередь очищена",
            description=f"Удалено треков: **{cleared_count}**",
            color=discord.Color.orange()
        )
        
        await interaction.response.send_message(embed=embed)
    

