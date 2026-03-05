import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import logging
from typing import Optional
from datetime import datetime, timezone
import os

from src.config import Config
from src.database import (
    DatabaseManager, UserDatabase, TopDatabase,
    LevelDatabase, SettingsDatabase, ShopDatabase,
    TransactionDatabase, TwitchDatabase
)
from src.image_generator import ProfileImageGenerator
from src.commands.admin_commands import AdminCommands
from src.commands.economy_commands import EconomyCommands
from src.commands.top_commands import TopCommands
from src.commands.profile_commands import ProfileCommands
from src.commands.global_commands import GlobalCommands
from src.commands.voice_commands import VoiceCommands
from src.commands.music_commands import MusicCommands
from src.commands.verify_commands import VerifyCommands
from src.commands.level_commands import LevelCommands
from src.commands.daily_commands import DailyCommands
from src.commands.games_commands import GamesCommands
from src.commands.shop_commands import ShopCommands
from src.commands.twitch_commands import TwitchCommands
from src.commands.drops_commands import DropsCommands
from src.commands.logging_commands import LoggingCommands
from src.services.level_service import LevelService
from src.services.twitch_service import TwitchService
from src.services.logging_service import LoggingService

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class DiscordBot(commands.Bot):
    """Main Discord bot class"""

    def __init__(self):
        intents = discord.Intents.all()
        intents.members = True
        super().__init__(command_prefix='!', intents=intents)

        # Config
        self.config = Config()

        self._last_backup_date = None

        # Global commands
        self.global_commands = GlobalCommands(self)
        self.tree.add_command(self.global_commands)

        @self.tree.command(name="ping", guild=None)
        async def ping(interaction: discord.Interaction):
            await interaction.response.send_message(
                f"Понг!",
                ephemeral=True
            )

        # Database
        self.db_manager = DatabaseManager(self.config.DATABASE_PATH)
        self.user_db = UserDatabase(self.db_manager)
        self.top_db = TopDatabase(self.db_manager)
        self.level_db = LevelDatabase(self.db_manager)
        self.settings_db = SettingsDatabase(self.db_manager)
        self.shop_db = ShopDatabase(self.db_manager)
        self.transaction_db = TransactionDatabase(self.db_manager)
        self.twitch_db = TwitchDatabase(self.db_manager)

        # Image generator
        self.image_generator = ProfileImageGenerator()

        # Services
        self.level_service = LevelService(self)
        self.twitch_service = TwitchService(
            self.config.TWITCH_CLIENT_ID,
            self.config.TWITCH_CLIENT_SECRET
        )
        self.logging_service = LoggingService(self)

        # Commands
        self.admin_commands = AdminCommands(self, self.user_db)
        self.economy_commands = EconomyCommands(self, self.user_db)
        self.top_commands = TopCommands(self, self.top_db)
        self.profile_commands = ProfileCommands(self, self.user_db)
        self.voice_commands = VoiceCommands(self)
        self.music_commands = MusicCommands(self)
        self.verify_commands = VerifyCommands(self)
        self.level_commands = LevelCommands(self)
        self.daily_commands = DailyCommands(self)
        self.games_commands = GamesCommands(self)
        self.shop_commands = ShopCommands(self)
        self.twitch_commands_handler = TwitchCommands(self)
        self.drops_commands = DropsCommands(self)
        self.logging_commands = LoggingCommands(self)

        # Events & commands
        self.setup_events()
        self.setup_commands()

        # Tasks
        self.voice_check.change_interval(minutes=self.config.VOICE_CHECK_INTERVAL)
        self.voice_check.start()
        self.database_backup.start()
        if self.twitch_service.enabled:
            self.twitch_check.change_interval(minutes=self.config.TWITCH_CHECK_INTERVAL)
            self.twitch_check.start()
            self.drops_check.start()

        logger.info("DiscordBot initialized")

    def setup_events(self):
        """Setup bot events"""

        @self.event
        async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
            await self.voice_commands.handle_voice_state_update(member, before, after)

            # Check if music bot should disconnect
            if before.channel and not member.bot:
                guild_id = before.channel.guild.id
                vc = self.music_commands.player.get_voice_client(guild_id)
                if vc and vc.channel and vc.channel.id == before.channel.id:
                    human_members = [m for m in before.channel.members if not m.bot]
                    if len(human_members) == 0:
                        await self.music_commands.player.check_inactivity(guild_id)

            # Logging
            await self.logging_service.log_voice_state(member, before, after)

        @self.event
        async def on_ready():
            logger.info(f'{self.user} connected to Discord!')

            try:
                await self.tree.sync()
                logger.info("Global commands synced")
                await self.tree.sync(guild=discord.Object(id=self.config.GUILD_ID))
                logger.info("Guild commands synced")
            except Exception as e:
                logger.error(f"Command sync error: {e}")

            activity = discord.Activity(
                type=discord.ActivityType.listening,
                name=self.config.BOT_ACTIVITY_NAME
            )
            await self.change_presence(
                activity=activity,
                status=discord.Status.do_not_disturb
            )
            logger.info('Sombra Online')

        @self.event
        async def on_message(message):
            if message.author.bot:
                return

            await self.handle_message_statistics(message)

            # Level XP from messages
            if not message.author.bot:
                if not await self.user_db.user_exists(message.author.id):
                    await self.user_db.add_user(message.author.id)

                result = await self.level_service.add_message_xp(message.author.id)
                if result:
                    new_level, leveled_up = result
                    if leveled_up:
                        await self._handle_level_up(message, new_level)

            await self.process_commands(message)

        @self.event
        async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
            await self.verify_commands.handle_reaction(payload)

        # Logging events
        @self.event
        async def on_message_edit(before: discord.Message, after: discord.Message):
            if before.author.bot:
                return
            await self.logging_service.log_message_edit(before, after)

        @self.event
        async def on_message_delete(message: discord.Message):
            if message.author.bot:
                return
            await self.logging_service.log_message_delete(message)

        @self.event
        async def on_member_join(member: discord.Member):
            await self.logging_service.log_member_join(member)

        @self.event
        async def on_member_remove(member: discord.Member):
            await self.logging_service.log_member_leave(member)

        @self.event
        async def on_member_update(before: discord.Member, after: discord.Member):
            await self.logging_service.log_member_update(before, after)

        @self.event
        async def on_member_ban(guild: discord.Guild, user: discord.User):
            await self.logging_service.log_ban(guild, user)

        @self.event
        async def on_member_unban(guild: discord.Guild, user: discord.User):
            await self.logging_service.log_unban(guild, user)

        @self.event
        async def on_guild_channel_create(channel: discord.abc.GuildChannel):
            await self.logging_service.log_channel_create(channel)

        @self.event
        async def on_guild_channel_delete(channel: discord.abc.GuildChannel):
            await self.logging_service.log_channel_delete(channel)

        @self.event
        async def on_guild_channel_update(before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
            await self.logging_service.log_channel_update(before, after)

        @self.event
        async def on_guild_role_create(role: discord.Role):
            await self.logging_service.log_role_create(role)

        @self.event
        async def on_guild_role_delete(role: discord.Role):
            await self.logging_service.log_role_delete(role)

        @self.event
        async def on_guild_role_update(before: discord.Role, after: discord.Role):
            await self.logging_service.log_role_update(before, after)

    async def _handle_level_up(self, message, new_level: int):
        """Handle level-up notification and role assignment"""
        try:
            embed = discord.Embed(
                title="Новый уровень!",
                description=f"{message.author.mention} достиг уровня **{new_level}**!",
                color=discord.Color.gold()
            )
            await message.channel.send(embed=embed)

            member = message.guild.get_member(message.author.id)
            if member:
                await self.level_service.check_level_roles(member, new_level)
        except Exception as e:
            logger.error(f"Level up handler error: {e}")

    @tasks.loop(minutes=1)  # overridden in __init__ via change_interval
    async def voice_check(self):
        """Check users in voice channels every minute"""
        try:
            for guild in self.guilds:
                for channel in guild.voice_channels:
                    for member in channel.members:
                        if not member.bot and not member.voice.self_deaf and not member.voice.afk:
                            if not await self.user_db.user_exists(member.id):
                                await self.user_db.add_user(member.id)

                            if not member.voice.self_mute:
                                await self.user_db.add_voice_time(member.id, self.config.VOICE_TIME_REWARD)
                                await self.user_db.add_money(member.id, self.config.VOICE_MONEY_REWARD)

                                new_balance = await self.user_db.get_money(member.id)
                                await self.transaction_db.log(
                                    member.id, 'voice_reward',
                                    self.config.VOICE_MONEY_REWARD,
                                    new_balance
                                )

                                new_level, leveled_up = await self.level_service.add_voice_xp(member.id)
                                if leveled_up:
                                    await self.level_service.check_level_roles(member, new_level)
        except Exception as e:
            logger.error(f"Voice check error: {e}")

    @voice_check.before_loop
    async def before_voice_check(self):
        await self.wait_until_ready()

    @tasks.loop(hours=24)
    async def database_backup(self):
        """Send database backup on the 4th of each month"""
        try:
            today = datetime.now(timezone.utc)
            today_date = today.date()

            if today.day == 4:
                if self._last_backup_date == today_date:
                    return

                backup_channel_id = self.config.BACKUP_CHANNEL_ID
                if not backup_channel_id:
                    return

                channel = self.get_channel(backup_channel_id)
                if not channel:
                    logger.warning(f"Backup channel {backup_channel_id} not found")
                    return

                db_path = self.config.DATABASE_PATH
                if not os.path.exists(db_path):
                    logger.warning(f"Database file {db_path} not found")
                    return

                try:
                    with open(db_path, 'rb') as db_file:
                        date_str = today.strftime('%Y-%m-%d')
                        filename = f"backup_{date_str}_{os.path.basename(db_path)}"
                        file = discord.File(db_file, filename=filename)
                        await channel.send(
                            f"Backup {date_str}",
                            file=file
                        )
                        self._last_backup_date = today_date
                        logger.info(f"Database backup sent to {backup_channel_id}")
                except Exception as e:
                    logger.error(f"Backup send error: {e}")

        except Exception as e:
            logger.error(f"Backup task error: {e}")

    @database_backup.before_loop
    async def before_database_backup(self):
        await self.wait_until_ready()
        await asyncio.sleep(60)

    @tasks.loop(minutes=3)  # overridden in __init__ via change_interval
    async def twitch_check(self):
        """Check Twitch streams periodically"""
        try:
            streamers = await self.twitch_db.get_streamers()
            if not streamers:
                return

            usernames = [s[1] for s in streamers]
            live_streams = await self.twitch_service.check_streams(usernames)
            live_usernames = {s['user_login'].lower() for s in live_streams}

            channel_id_str = await self.settings_db.get('twitch_channel_id')
            if not channel_id_str:
                return
            channel = self.get_channel(int(channel_id_str))
            if not channel:
                return

            ping_role_str = await self.settings_db.get('twitch_ping_role_id')

            for streamer in streamers:
                _, username, twitch_id, was_live, last_stream_id = streamer
                is_live_now = username.lower() in live_usernames

                if is_live_now and not was_live:
                    # Just went live
                    stream_data = next(
                        (s for s in live_streams if s['user_login'].lower() == username.lower()),
                        None
                    )
                    if stream_data:
                        stream_id = stream_data.get('id')
                        if stream_id == last_stream_id:
                            continue

                        embed = discord.Embed(
                            title=stream_data.get('title', 'Live Stream'),
                            url=f"https://twitch.tv/{username}",
                            color=0x9146FF
                        )
                        embed.set_author(name=f"{stream_data.get('user_name', username)} is live!")
                        embed.add_field(name="Game", value=stream_data.get('game_name', 'Unknown'), inline=True)
                        embed.add_field(name="Viewers", value=str(stream_data.get('viewer_count', 0)), inline=True)

                        thumbnail = stream_data.get('thumbnail_url', '')
                        if thumbnail:
                            thumbnail = thumbnail.replace('{width}', '440').replace('{height}', '248')
                            embed.set_image(url=thumbnail)

                        content = ""
                        if ping_role_str:
                            content = f"<@&{ping_role_str}>"

                        view = discord.ui.View()
                        view.add_item(discord.ui.Button(
                            label="Watch",
                            url=f"https://twitch.tv/{username}",
                            style=discord.ButtonStyle.link
                        ))

                        await channel.send(content=content, embed=embed, view=view)
                        await self.twitch_db.set_live_status(username, True, stream_id)

                elif not is_live_now and was_live:
                    await self.twitch_db.set_live_status(username, False)

        except Exception as e:
            logger.error(f"Twitch check error: {e}")

    @twitch_check.before_loop
    async def before_twitch_check(self):
        await self.wait_until_ready()

    @tasks.loop(minutes=15)
    async def drops_check(self):
        """Check Twitch drops campaigns"""
        try:
            games = await self.twitch_db.get_drops_games()
            if not games:
                return

            game_ids = [g[2] for g in games if g[2]]
            if not game_ids:
                return

            campaigns = await self.twitch_service.check_drops(game_ids)
            if not campaigns:
                return

            channel_id_str = await self.settings_db.get('drops_channel_id')
            if not channel_id_str:
                return
            channel = self.get_channel(int(channel_id_str))
            if not channel:
                return

            for campaign in campaigns:
                embed = discord.Embed(
                    title=campaign.get('name', 'Drops Campaign'),
                    color=0x00FF00
                )
                embed.add_field(
                    name="Game",
                    value=campaign.get('game', {}).get('name', 'Unknown'),
                    inline=True
                )
                if campaign.get('start_at'):
                    embed.add_field(name="Start", value=campaign['start_at'][:10], inline=True)
                if campaign.get('end_at'):
                    embed.add_field(name="End", value=campaign['end_at'][:10], inline=True)

                await channel.send(embed=embed)

        except Exception as e:
            logger.error(f"Drops check error: {e}")

    @drops_check.before_loop
    async def before_drops_check(self):
        await self.wait_until_ready()

    def setup_commands(self):
        """Setup bot commands"""
        guild_obj = discord.Object(id=self.config.GUILD_ID)

        @self.tree.command(name="help", description="Список команд", guild=guild_obj)
        async def help(interaction: discord.Interaction):
            help_text = (
                '/profile - Ваша статистика на сервере\n'
                '/rank - Уровень и XP\n'
                '/daily - Ежедневный бонус\n\n'
                '**Банковские операции**\n'
                '/transfer - перевести деньги пользователю (комиссия 10%)\n\n'
                '**Игры**\n'
                '/coinflip - подбросить монетку (x1.8)\n'
                '/dice - кости (x2)\n'
                '/duel - дуэль с игроком\n\n'
                '**Магазин**\n'
                '/shop - магазин предметов\n'
                '/buy - купить предмет\n'
                '/inventory - инвентарь\n'
                '/equip - экипировать предмет\n\n'
                '**Топ участников**\n'
                '/voice - топ по времени в войсе\n'
                '/messages - топ по сообщениям\n'
                '/balance - топ по балансу\n'
                '/leaderboard - топ по уровням\n\n'
                '**Музыка**\n'
                '/play - воспроизвести трек\n'
                '/skip - пропустить трек\n'
                '/queue - очередь воспроизведения\n'
                '/stop - остановить\n'
                '/pause - пауза/возобновление\n\n'
                '**Административные команды**\n'
                '/ban - забанить\n'
                '/kick - кикнуть\n'
                '/mute - замутить\n'
                '/give - выдать деньги\n'
                '/rem - снять деньги'
            )
            await interaction.response.send_message(help_text, ephemeral=True)

        @self.tree.command(name="profile", description="Ваш профиль и статистика", guild=guild_obj)
        async def profile(interaction: discord.Interaction, user: discord.Member = None):
            if user is None:
                user = interaction.user
            await self.profile_commands.show_profile(interaction, user)

        # Admin commands
        @self.tree.command(name="ban", description="Забанить пользователя (бан вечный)", guild=guild_obj)
        async def ban(interaction: discord.Interaction, user: discord.Member, reason: str):
            await self.admin_commands.ban_user(interaction, user, reason)

        @self.tree.command(name="kick", description="Кикнуть пользователя", guild=guild_obj)
        async def kick(interaction: discord.Interaction, user: discord.Member, reason: str):
            await self.admin_commands.kick_user(interaction, user, reason)

        @self.tree.command(name="mute", description="Замутить пользователя (время в минутах, макс 38880)", guild=guild_obj)
        async def mute(interaction: discord.Interaction, user: discord.Member, reason: str, time: int):
            await self.admin_commands.mute_user(interaction, user, reason, time)

        @self.tree.command(name="give", description="Выдать деньги пользователю (только для админа)", guild=guild_obj)
        async def give(interaction: discord.Interaction, user: discord.Member, amount: int):
            await self.admin_commands.give_money(interaction, user, amount)

        @self.tree.command(name="rem", description="Снять деньги у пользователя (только для админа)", guild=guild_obj)
        async def rem(interaction: discord.Interaction, user: discord.Member, amount: int):
            await self.admin_commands.remove_money(interaction, user, amount)

        @self.tree.command(name="economy_reset", description="Сбросить баланс пользователя", guild=guild_obj)
        async def economy_reset(interaction: discord.Interaction, user: discord.Member):
            if not self.admin_commands.has_admin_role(interaction.user):
                await interaction.response.send_message('No permission', ephemeral=True)
                return
            await self.user_db.reset_money(user.id)
            new_balance = await self.user_db.get_money(user.id)
            await self.transaction_db.log(user.id, 'admin_rem', 0, new_balance, f'reset by {interaction.user.id}')
            await interaction.response.send_message(f'Balance reset for {user.mention}', ephemeral=True)

        # Economy commands
        @self.tree.command(name="transfer", description="Перевести деньги пользователю (комиссия 10%)", guild=guild_obj)
        async def transfer(interaction: discord.Interaction, user: discord.Member, amount: int):
            await self.economy_commands.transfer_money(interaction, user, amount)

        # Top commands
        @self.tree.command(name="voice", description="Топ по времени в голосовых каналах", guild=guild_obj)
        async def voice(interaction: discord.Interaction):
            await self.top_commands.show_voice_top(interaction)

        @self.tree.command(name="messages", description="Топ по сообщениям", guild=guild_obj)
        async def messages(interaction: discord.Interaction):
            await self.top_commands.show_messages_top(interaction)

        @self.tree.command(name="balance", description="Топ по балансу", guild=guild_obj)
        async def balance(interaction: discord.Interaction):
            await self.top_commands.show_balance_top(interaction)

        # Level commands
        @self.tree.command(name="rank", description="Уровень и XP", guild=guild_obj)
        async def rank(interaction: discord.Interaction, user: discord.Member = None):
            await self.level_commands.show_rank(interaction, user)

        @self.tree.command(name="leaderboard", description="Топ по уровням", guild=guild_obj)
        async def leaderboard(interaction: discord.Interaction, page: int = 1):
            await self.level_commands.show_leaderboard(interaction, page)

        # Daily
        @self.tree.command(name="daily", description="Ежедневный бонус", guild=guild_obj)
        async def daily(interaction: discord.Interaction):
            await self.daily_commands.claim_daily(interaction)

        # Games
        @self.tree.command(name="coinflip", description="Подбросить монетку (выигрыш x1.8)", guild=guild_obj)
        @app_commands.describe(amount="Сумма ставки")
        async def coinflip(interaction: discord.Interaction, amount: int):
            await self.games_commands.coinflip(interaction, amount)

        @self.tree.command(name="dice", description="Кости - ваш бросок против бота (выигрыш x2)", guild=guild_obj)
        @app_commands.describe(amount="Сумма ставки")
        async def dice(interaction: discord.Interaction, amount: int):
            await self.games_commands.dice(interaction, amount)

        @self.tree.command(name="duel", description="Дуэль с другим игроком", guild=guild_obj)
        @app_commands.describe(user="Противник", amount="Сумма ставки")
        async def duel(interaction: discord.Interaction, user: discord.Member, amount: int):
            await self.games_commands.duel(interaction, user, amount)

        # Shop
        @self.tree.command(name="shop", description="Магазин предметов", guild=guild_obj)
        async def shop(interaction: discord.Interaction):
            await self.shop_commands.show_shop(interaction)

        @self.tree.command(name="buy", description="Купить предмет из магазина", guild=guild_obj)
        @app_commands.describe(item_id="ID предмета")
        async def buy(interaction: discord.Interaction, item_id: int):
            await self.shop_commands.buy_item(interaction, item_id)

        @self.tree.command(name="inventory", description="Ваш инвентарь", guild=guild_obj)
        async def inventory(interaction: discord.Interaction):
            await self.shop_commands.show_inventory(interaction)

        @self.tree.command(name="equip", description="Экипировать предмет", guild=guild_obj)
        @app_commands.describe(item_id="ID предмета")
        async def equip(interaction: discord.Interaction, item_id: int):
            await self.shop_commands.equip_item(interaction, item_id)

        @self.tree.command(name="shop_add", description="Добавить предмет в магазин (админ)", guild=guild_obj)
        @app_commands.describe(category="Категория (role/background/badge)", name="Название", price="Цена", description="Описание", data="JSON данные")
        async def shop_add(interaction: discord.Interaction, category: str, name: str, price: int,
                           description: str = None, data: str = None):
            await self.shop_commands.admin_add_item(interaction, category, name, price, description, data)

        @self.tree.command(name="shop_remove", description="Удалить предмет из магазина (админ)", guild=guild_obj)
        @app_commands.describe(item_id="ID предмета")
        async def shop_remove(interaction: discord.Interaction, item_id: int):
            await self.shop_commands.admin_remove_item(interaction, item_id)

        @self.tree.command(name="shop_edit", description="Редактировать предмет магазина (админ)", guild=guild_obj)
        @app_commands.describe(item_id="ID предмета", field="Поле (name/description/price/item_data/category)", value="Новое значение")
        async def shop_edit(interaction: discord.Interaction, item_id: int, field: str, value: str):
            await self.shop_commands.admin_edit_item(interaction, item_id, field, value)

        # Verify
        @self.tree.command(name="verify_setup", description="Настроить верификацию (админ)", guild=guild_obj)
        @app_commands.describe(title="Заголовок", description="Описание", color="Цвет (#HEX)", image_url="URL изображения", emoji="Эмодзи для реакции", role="Роль для выдачи")
        async def verify_setup(interaction: discord.Interaction, title: str, description: str,
                               color: str, image_url: str, emoji: str, role: discord.Role):
            await self.verify_commands.setup_verify(interaction, title, description, color, image_url, emoji, role)

        @self.tree.command(name="verify_edit", description="Редактировать верификацию (админ)", guild=guild_obj)
        @app_commands.describe(title="Заголовок", description="Описание", color="Цвет (#HEX)", image_url="URL изображения")
        async def verify_edit(interaction: discord.Interaction, title: str = None, description: str = None,
                              color: str = None, image_url: str = None):
            await self.verify_commands.edit_verify(interaction, title, description, color, image_url)

        # Twitch
        @self.tree.command(name="twitch_add", description="Добавить стримера (админ)", guild=guild_obj)
        @app_commands.describe(username="Twitch username")
        async def twitch_add(interaction: discord.Interaction, username: str):
            await self.twitch_commands_handler.add_streamer(interaction, username)

        @self.tree.command(name="twitch_remove", description="Удалить стримера (админ)", guild=guild_obj)
        @app_commands.describe(username="Twitch username")
        async def twitch_remove(interaction: discord.Interaction, username: str):
            await self.twitch_commands_handler.remove_streamer(interaction, username)

        @self.tree.command(name="twitch_list", description="Список отслеживаемых стримеров", guild=guild_obj)
        async def twitch_list(interaction: discord.Interaction):
            await self.twitch_commands_handler.list_streamers(interaction)

        @self.tree.command(name="twitch_channel", description="Канал для уведомлений Twitch (админ)", guild=guild_obj)
        @app_commands.describe(channel="Текстовый канал")
        async def twitch_channel(interaction: discord.Interaction, channel: discord.TextChannel):
            await self.twitch_commands_handler.set_channel(interaction, channel)

        @self.tree.command(name="twitch_pingrole", description="Роль для пинга стримов (админ)", guild=guild_obj)
        @app_commands.describe(role="Роль")
        async def twitch_pingrole(interaction: discord.Interaction, role: discord.Role):
            await self.twitch_commands_handler.set_ping_role(interaction, role)

        # Drops
        @self.tree.command(name="drops_add", description="Добавить игру для отслеживания дропсов (админ)", guild=guild_obj)
        @app_commands.describe(game_name="Название игры")
        async def drops_add(interaction: discord.Interaction, game_name: str):
            await self.drops_commands.add_game(interaction, game_name)

        @self.tree.command(name="drops_remove", description="Убрать игру из отслеживания дропсов (админ)", guild=guild_obj)
        @app_commands.describe(game_name="Название игры")
        async def drops_remove(interaction: discord.Interaction, game_name: str):
            await self.drops_commands.remove_game(interaction, game_name)

        @self.tree.command(name="drops_channel", description="Канал для дропсов (админ)", guild=guild_obj)
        @app_commands.describe(channel="Текстовый канал")
        async def drops_channel(interaction: discord.Interaction, channel: discord.TextChannel):
            await self.drops_commands.set_channel(interaction, channel)

        # Logging
        @self.tree.command(name="logs", description="Установить канал для логов (админ)", guild=guild_obj)
        @app_commands.describe(channel="Текстовый канал")
        async def logs(interaction: discord.Interaction, channel: discord.TextChannel):
            await self.logging_commands.set_log_channel(interaction, channel)

        # Music commands
        @self.tree.command(name="play", description="Воспроизвести трек (YouTube/Spotify URL или поиск)", guild=guild_obj)
        @app_commands.describe(query="URL или название трека")
        async def play(interaction: discord.Interaction, query: str):
            await self.music_commands.play(interaction, query)

        @self.tree.command(name="skip", description="Пропустить текущий трек", guild=guild_obj)
        async def skip(interaction: discord.Interaction):
            await self.music_commands.skip(interaction)

        @self.tree.command(name="queue", description="Показать очередь воспроизведения", guild=guild_obj)
        async def queue(interaction: discord.Interaction):
            await self.music_commands.show_queue(interaction)

        @self.tree.command(name="stop", description="Остановить воспроизведение и очистить очередь", guild=guild_obj)
        async def stop(interaction: discord.Interaction):
            await self.music_commands.stop(interaction)

        @self.tree.command(name="pause", description="Поставить на паузу или возобновить воспроизведение", guild=guild_obj)
        async def pause(interaction: discord.Interaction):
            await self.music_commands.pause(interaction)

        @self.tree.command(name="loop", description="Переключить режим повтора (трек/очередь/выкл)", guild=guild_obj)
        async def loop(interaction: discord.Interaction):
            await self.music_commands.loop(interaction)

        @self.tree.command(name="clear", description="Очистить очередь треков (только модератор)", guild=guild_obj)
        async def clear(interaction: discord.Interaction):
            await self.music_commands.clear(interaction)

    async def handle_message_statistics(self, message):
        """Handle message statistics"""
        try:
            if not await self.user_db.user_exists(message.author.id):
                await self.user_db.add_user(message.author.id)
                await self.user_db.add_message(message.author.id, self.config.INITIAL_MESSAGES)
                await self.user_db.add_money(message.author.id, self.config.INITIAL_MONEY)
            else:
                await self.user_db.add_message(message.author.id, 1)
        except Exception as e:
            logger.error(f"Message statistics error: {e}")

    async def run_bot(self):
        """Start the bot"""
        try:
            await self.start(self.config.DISCORD_TOKEN)
        except Exception as e:
            logger.error(f"Bot start error: {e}")
            raise
