import discord
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Color scheme
COLOR_DELETE = 0xFF0000      # Red
COLOR_JOIN = 0x00FF00        # Green
COLOR_EDIT = 0xFFFF00        # Yellow
COLOR_LEAVE = 0xFF8C00       # Orange
COLOR_VOICE = 0x0000FF       # Blue
COLOR_ROLE = 0x800080        # Purple


class LoggingService:
    """Service for server event logging"""

    def __init__(self, bot):
        self.bot = bot

    async def _get_log_channel(self) -> Optional[discord.TextChannel]:
        """Get the configured log channel, or None if not set"""
        try:
            channel_id = await self.bot.settings_db.get('log_channel_id')
            if channel_id:
                return self.bot.get_channel(int(channel_id))
        except Exception:
            pass
        return None

    async def _send_log(self, embed: discord.Embed):
        """Send a log embed to the log channel"""
        channel = await self._get_log_channel()
        if not channel:
            return
        try:
            await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed to send log: {e}")

    async def log_message_edit(self, before: discord.Message, after: discord.Message):
        if before.content == after.content:
            return
        embed = discord.Embed(
            title="Message Edited",
            color=COLOR_EDIT,
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name=str(before.author), icon_url=before.author.display_avatar.url)
        embed.add_field(name="Before", value=before.content[:1024] or "*empty*", inline=False)
        embed.add_field(name="After", value=after.content[:1024] or "*empty*", inline=False)
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        embed.set_footer(text=f"Message ID: {before.id} | Author ID: {before.author.id}")
        await self._send_log(embed)

    async def log_message_delete(self, message: discord.Message):
        embed = discord.Embed(
            title="Message Deleted",
            color=COLOR_DELETE,
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
        embed.add_field(name="Content", value=message.content[:1024] or "*empty*", inline=False)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        embed.set_footer(text=f"Message ID: {message.id} | Author ID: {message.author.id}")
        await self._send_log(embed)

    async def log_member_join(self, member: discord.Member):
        embed = discord.Embed(
            title="Member Joined",
            description=f"{member.mention} ({member})",
            color=COLOR_JOIN,
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Account Created", value=member.created_at.strftime("%d.%m.%Y %H:%M"), inline=True)
        embed.add_field(name="Member Count", value=str(member.guild.member_count), inline=True)
        embed.set_footer(text=f"ID: {member.id}")
        await self._send_log(embed)

    async def log_member_leave(self, member: discord.Member):
        embed = discord.Embed(
            title="Member Left",
            description=f"{member.mention} ({member})",
            color=COLOR_LEAVE,
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        roles = [r.mention for r in member.roles[1:]]  # Skip @everyone
        if roles:
            embed.add_field(name="Roles", value=", ".join(roles)[:1024], inline=False)
        embed.set_footer(text=f"ID: {member.id}")
        await self._send_log(embed)

    async def log_member_update(self, before: discord.Member, after: discord.Member):
        # Role changes
        added_roles = set(after.roles) - set(before.roles)
        removed_roles = set(before.roles) - set(after.roles)

        if added_roles or removed_roles:
            embed = discord.Embed(
                title="Member Roles Updated",
                description=f"{after.mention}",
                color=COLOR_ROLE,
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(name=str(after), icon_url=after.display_avatar.url)
            if added_roles:
                embed.add_field(name="Added", value=", ".join(r.mention for r in added_roles), inline=False)
            if removed_roles:
                embed.add_field(name="Removed", value=", ".join(r.mention for r in removed_roles), inline=False)
            embed.set_footer(text=f"ID: {after.id}")
            await self._send_log(embed)

        # Nickname changes
        if before.nick != after.nick:
            embed = discord.Embed(
                title="Nickname Changed",
                description=f"{after.mention}",
                color=COLOR_EDIT,
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="Before", value=before.nick or before.name, inline=True)
            embed.add_field(name="After", value=after.nick or after.name, inline=True)
            embed.set_footer(text=f"ID: {after.id}")
            await self._send_log(embed)

    async def log_voice_state(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if before.channel == after.channel:
            return

        embed = discord.Embed(color=COLOR_VOICE, timestamp=discord.utils.utcnow())
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)

        if before.channel is None and after.channel is not None:
            embed.title = "Joined Voice Channel"
            embed.add_field(name="Channel", value=after.channel.mention, inline=True)
        elif before.channel is not None and after.channel is None:
            embed.title = "Left Voice Channel"
            embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        else:
            embed.title = "Switched Voice Channel"
            embed.add_field(name="From", value=before.channel.mention, inline=True)
            embed.add_field(name="To", value=after.channel.mention, inline=True)

        embed.set_footer(text=f"ID: {member.id}")
        await self._send_log(embed)

    async def log_ban(self, guild: discord.Guild, user: discord.User):
        embed = discord.Embed(
            title="Member Banned",
            description=f"{user.mention} ({user})",
            color=COLOR_DELETE,
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"ID: {user.id}")
        await self._send_log(embed)

    async def log_unban(self, guild: discord.Guild, user: discord.User):
        embed = discord.Embed(
            title="Member Unbanned",
            description=f"{user.mention} ({user})",
            color=COLOR_JOIN,
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"ID: {user.id}")
        await self._send_log(embed)

    async def log_channel_create(self, channel: discord.abc.GuildChannel):
        embed = discord.Embed(
            title="Channel Created",
            description=f"{channel.mention} (`{channel.name}`)",
            color=COLOR_JOIN,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Type", value=str(channel.type), inline=True)
        embed.set_footer(text=f"ID: {channel.id}")
        await self._send_log(embed)

    async def log_channel_delete(self, channel: discord.abc.GuildChannel):
        embed = discord.Embed(
            title="Channel Deleted",
            description=f"`{channel.name}`",
            color=COLOR_DELETE,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Type", value=str(channel.type), inline=True)
        embed.set_footer(text=f"ID: {channel.id}")
        await self._send_log(embed)

    async def log_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        if before.name == after.name:
            return
        embed = discord.Embed(
            title="Channel Updated",
            description=after.mention,
            color=COLOR_EDIT,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Before", value=before.name, inline=True)
        embed.add_field(name="After", value=after.name, inline=True)
        embed.set_footer(text=f"ID: {after.id}")
        await self._send_log(embed)

    async def log_role_create(self, role: discord.Role):
        embed = discord.Embed(
            title="Role Created",
            description=f"{role.mention} (`{role.name}`)",
            color=COLOR_JOIN,
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"ID: {role.id}")
        await self._send_log(embed)

    async def log_role_delete(self, role: discord.Role):
        embed = discord.Embed(
            title="Role Deleted",
            description=f"`{role.name}`",
            color=COLOR_DELETE,
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"ID: {role.id}")
        await self._send_log(embed)

    async def log_role_update(self, before: discord.Role, after: discord.Role):
        changes = []
        if before.name != after.name:
            changes.append(f"Name: `{before.name}` -> `{after.name}`")
        if before.color != after.color:
            changes.append(f"Color: `{before.color}` -> `{after.color}`")
        if before.permissions != after.permissions:
            changes.append("Permissions changed")

        if not changes:
            return

        embed = discord.Embed(
            title="Role Updated",
            description=f"{after.mention}\n" + "\n".join(changes),
            color=COLOR_ROLE,
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"ID: {after.id}")
        await self._send_log(embed)
