import discord
from discord.ext import commands
from typing import Optional
from .base_command import BaseCommand
from ..database import UserDatabase

class AdminCommands(BaseCommand):
    """Класс для административных команд"""

    def __init__(self, bot: commands.Bot, user_db: UserDatabase):
        super().__init__(bot)
        self.user_db = user_db
        self.config = self.bot.config
        # Role hierarchy from config
        self.role_hierarchy = self.config.ROLE_HIERARCHY

    def get_role_level(self, member: discord.Member) -> int:
        """Получает уровень роли пользователя в иерархии"""
        for i, role_id in enumerate(self.role_hierarchy):
            if any(role.id == role_id for role in member.roles):
                return i
        return len(self.role_hierarchy)  # Возвращаем значение ниже всех ролей если ни одной нет

    def can_moderate(self, moderator: discord.Member, target: discord.Member) -> bool:
        """Проверяет, может ли модератор применять действия к цели"""
        mod_level = self.get_role_level(moderator)
        target_level = self.get_role_level(target)
        return mod_level < target_level  # True если роль модератора выше (меньше индекс)

    def has_admin_role(self, member: discord.Member) -> bool:
        """Проверяет, есть ли у пользователя права полного администратора"""
        return any(role.id in [self.config.ADMIN_ROLE_LVL0, self.config.ADMIN_ROLE_LVL1] for role in member.roles)

    def has_mod_role(self, member: discord.Member) -> bool:
        """Проверяет, есть ли у пользователя права модератора"""
        return any(role.id == self.config.ADMIN_ROLE_LVL2 for role in member.roles)

    async def ban_user(self, interaction: discord.Interaction, user: discord.Member, reason: str) -> None:
        """Банит пользователя"""
        if not self.has_admin_role(interaction.user):
            await interaction.response.send_message('У вас нет прав для выполнения этой команды', ephemeral=True)
            return

        if not self.can_moderate(interaction.user, user):
            await interaction.response.send_message('Вы не можете забанить пользователя с равной или более высокой ролью', ephemeral=True)
            return

        try:
            # Отправляем сообщение о бане в личку
            channel = await user.create_dm()
            embed = discord.Embed(
                color=0xff0000,
                title='Бан',
                description=f'Вас забанили\nПо причине: {reason} by {interaction.user.mention}'
            )
            embed.set_footer(text=str(interaction.user), icon_url=interaction.user.avatar)
            await channel.send(embed=embed)

            # Баним пользователя
            await user.ban(delete_message_days=7, reason=reason)

            await interaction.response.send_message(
                f'{user.mention}({user.id}) забанен {interaction.user.mention}\nПричина: {reason}',
                ephemeral=False
            )

        except Exception as e:
            await interaction.response.send_message(f'Ошибка при бане: {e}', ephemeral=True)

    async def kick_user(self, interaction: discord.Interaction, user: discord.Member, reason: str) -> None:
        """Кикает пользователя"""
        if not (self.has_admin_role(interaction.user) or self.has_mod_role(interaction.user)):
            await interaction.response.send_message('У вас нет прав для выполнения этой команды', ephemeral=True)
            return

        if not self.can_moderate(interaction.user, user):
            await interaction.response.send_message('Вы не можете кикнуть пользователя с равной или более высокой ролью', ephemeral=True)
            return

        try:
            # Отправляем сообщение о кике в личку
            channel = await user.create_dm()
            embed = discord.Embed(
                color=0xffa500,
                title='Кик',
                description=f'Вас кикнули\nПо причине: {reason} by {interaction.user.mention}'
            )
            embed.set_footer(text=str(interaction.user), icon_url=interaction.user.avatar)
            await channel.send(embed=embed)

            # Кикаем пользователя
            await user.kick(reason=reason)

            await interaction.response.send_message(
                f'{user.mention}({user.id}) кикнут {interaction.user.mention}\nПричина: {reason}',
                ephemeral=False
            )

        except Exception as e:
            await interaction.response.send_message(f'Ошибка при кике: {e}', ephemeral=True)

    async def mute_user(self, interaction: discord.Interaction, user: discord.Member, reason: str, time: int) -> None:
        """Мьютит пользователя"""
        if not (self.has_admin_role(interaction.user) or self.has_mod_role(interaction.user)):
            await interaction.response.send_message('У вас нет прав для выполнения этой команды', ephemeral=True)
            return

        if not self.can_moderate(interaction.user, user):
            await interaction.response.send_message('Вы не можете замьютить пользователя с равной или более высокой ролью', ephemeral=True)
            return

        if time > 38880:  # Максимум 38880 минут
            await interaction.response.send_message('Максимальное время мута: 38880 минут', ephemeral=True)
            return

        try:
            from datetime import timedelta
            import discord.utils

            # Отправляем сообщение о муте в личку
            channel = await user.create_dm()
            embed = discord.Embed(
                color=0xffff00,
                title='Мьют',
                description=f'Вы замьючены на {time} минут\nПо причине: {reason} by {interaction.user.mention}'
            )
            embed.set_footer(text=str(interaction.user), icon_url=interaction.user.avatar)
            await channel.send(embed=embed)

            # Мьютим пользователя
            timeout_until = discord.utils.utcnow() + timedelta(minutes=time)
            await user.edit(timed_out_until=timeout_until, reason=reason)

            await interaction.response.send_message(
                f'{user.mention}({user.id}) в мьюте на {time} минут {interaction.user.mention}\nПричина: {reason}',
                ephemeral=False
            )

        except Exception as e:
            await interaction.response.send_message(f'Ошибка при муте: {e}', ephemeral=True)
