import discord
import json
import logging
from .base_command import BaseCommand

logger = logging.getLogger(__name__)

CATEGORIES = ['role', 'background', 'badge']


class ShopCategorySelect(discord.ui.Select):
    """Category selector for the shop"""

    def __init__(self, shop_cmd):
        options = [
            discord.SelectOption(label="Все", value="all"),
            discord.SelectOption(label="Роли", value="role"),
            discord.SelectOption(label="Фоны", value="background"),
            discord.SelectOption(label="Значки", value="badge"),
        ]
        super().__init__(placeholder="Фильтр по категории...", options=options)
        self.shop_cmd = shop_cmd

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0] if self.values[0] != "all" else None
        embed = await self.shop_cmd._build_shop_embed(category)
        await interaction.response.edit_message(embed=embed)


class ShopView(discord.ui.View):
    def __init__(self, shop_cmd):
        super().__init__(timeout=120)
        self.add_item(ShopCategorySelect(shop_cmd))


class ShopCommands(BaseCommand):
    """Shop commands"""

    def __init__(self, bot):
        super().__init__(bot)

    async def _build_shop_embed(self, category: str = None) -> discord.Embed:
        items = await self.bot.shop_db.get_items(category)

        embed = discord.Embed(
            title="Магазин",
            color=discord.Color.gold()
        )

        if not items:
            embed.description = "Нет доступных предметов."
            return embed

        for item_id, name, desc, cat, price, data in items:
            value = f"{desc or 'Без описания'}\nЦена: **{price}** монет\nКатегория: `{cat}`"
            embed.add_field(name=f"#{item_id} - {name}", value=value, inline=False)

        return embed

    async def show_shop(self, interaction: discord.Interaction):
        """Show the shop"""
        await interaction.response.defer()
        embed = await self._build_shop_embed()
        view = ShopView(self)
        await interaction.followup.send(embed=embed, view=view)

    async def buy_item(self, interaction: discord.Interaction, item_id: int):
        """Buy an item from the shop"""
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id

        item = await self.bot.shop_db.get_item(item_id)
        if not item:
            await interaction.followup.send('Предмет не найден.', ephemeral=True)
            return

        _, name, desc, category, price, item_data = item

        # Check if already owned
        if await self.bot.shop_db.owns_item(user_id, item_id):
            await interaction.followup.send('Вы уже владеете этим предметом!', ephemeral=True)
            return

        # Check balance
        balance = await self.bot.user_db.get_money(user_id)
        if balance < price:
            await interaction.followup.send('Недостаточно денег!', ephemeral=True)
            return

        # Purchase
        await self.bot.user_db.rem_money(user_id, price)
        await self.bot.shop_db.add_to_inventory(user_id, item_id)

        new_balance = await self.bot.user_db.get_money(user_id)
        await self.bot.transaction_db.log(user_id, 'shop', -price, new_balance, f'buy:{name}')

        # If role item, assign role
        if category == 'role' and item_data:
            try:
                data = json.loads(item_data)
                role_id = data.get('role_id')
                if role_id:
                    guild = interaction.guild
                    role = guild.get_role(int(role_id))
                    if role:
                        await interaction.user.add_roles(role, reason=f"Покупка: {name}")
            except Exception as e:
                logger.error(f"Error assigning shop role: {e}")

        embed = discord.Embed(
            title="Покупка успешна!",
            description=f"Вы купили **{name}** за **{price}** монет.\nБаланс: **{new_balance}**",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def show_inventory(self, interaction: discord.Interaction):
        """Show user's inventory"""
        await interaction.response.defer(ephemeral=True)

        items = await self.bot.shop_db.get_inventory(interaction.user.id)

        embed = discord.Embed(title="Ваш инвентарь", color=discord.Color.blue())

        if not items:
            embed.description = "Ваш инвентарь пуст."
        else:
            for inv_id, name, desc, category, data in items:
                embed.add_field(
                    name=f"#{inv_id} - {name}",
                    value=f"{desc or '-'} | `{category}`",
                    inline=False
                )

        await interaction.followup.send(embed=embed, ephemeral=True)

    async def equip_item(self, interaction: discord.Interaction, item_id: int):
        """Equip an inventory item"""
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id

        if not await self.bot.shop_db.owns_item(user_id, item_id):
            await interaction.followup.send('Вы не владеете этим предметом.', ephemeral=True)
            return

        item = await self.bot.shop_db.get_item(item_id)
        if not item:
            await interaction.followup.send('Предмет не найден.', ephemeral=True)
            return

        _, name, _, category, _, _ = item

        if category not in ('background', 'badge'):
            await interaction.followup.send('Этот предмет нельзя экипировать.', ephemeral=True)
            return

        await self.bot.shop_db.equip_item(user_id, category, item_id)
        await interaction.followup.send(f'Экипировано: **{name}**!', ephemeral=True)

    async def admin_add_item(self, interaction: discord.Interaction, category: str, name: str,
                             price: int, description: str = None, data: str = None):
        """Admin: add shop item"""
        if not self.is_admin(interaction.user):
            await interaction.response.send_message('Нет прав', ephemeral=True)
            return

        if category not in CATEGORIES:
            await interaction.response.send_message(
                f'Неверная категория. Используйте: {", ".join(CATEGORIES)}', ephemeral=True)
            return

        await self.bot.shop_db.add_item(name, description, category, price, data)
        await interaction.response.send_message(f'Предмет **{name}** добавлен в магазин!', ephemeral=True)

    async def admin_remove_item(self, interaction: discord.Interaction, item_id: int):
        """Admin: remove shop item"""
        if not self.is_admin(interaction.user):
            await interaction.response.send_message('Нет прав', ephemeral=True)
            return

        await self.bot.shop_db.remove_item(item_id)
        await interaction.response.send_message(f'Предмет #{item_id} удален из магазина.', ephemeral=True)

    async def admin_edit_item(self, interaction: discord.Interaction, item_id: int, field: str, value: str):
        """Admin: edit shop item"""
        if not self.is_admin(interaction.user):
            await interaction.response.send_message('Нет прав', ephemeral=True)
            return

        success = await self.bot.shop_db.update_item(item_id, field, value)
        if success:
            await interaction.response.send_message(f'Предмет #{item_id} обновлен: {field} = {value}', ephemeral=True)
        else:
            await interaction.response.send_message(f'Ошибка. Допустимые поля: name, description, price, item_data, category', ephemeral=True)
