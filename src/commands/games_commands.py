import discord
import random
import time
import asyncio
import logging
from .base_command import BaseCommand

logger = logging.getLogger(__name__)


class DuelView(discord.ui.View):
    """View for duel accept/decline"""

    def __init__(self, challenger: discord.Member, target: discord.Member, amount: int, games_cmd):
        super().__init__(timeout=30)
        self.challenger = challenger
        self.target = target
        self.amount = amount
        self.games_cmd = games_cmd
        self.accepted = None

    @discord.ui.button(label="Принять", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target.id:
            await interaction.response.send_message("Эта дуэль не для вас!", ephemeral=True)
            return
        self.accepted = True
        self.stop()
        await self.games_cmd._resolve_duel(interaction, self)

    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target.id:
            await interaction.response.send_message("Эта дуэль не для вас!", ephemeral=True)
            return
        self.accepted = False
        self.stop()
        await interaction.response.send_message(
            f"{self.target.mention} отклонил дуэль.",
        )

    async def on_timeout(self):
        self.accepted = False


class GamesCommands(BaseCommand):
    """Mini-games commands"""

    def __init__(self, bot):
        super().__init__(bot)
        self._cooldowns: dict[int, float] = {}

    def _check_cooldown(self, user_id: int) -> bool:
        """Returns True if user is on cooldown"""
        now = time.time()
        last = self._cooldowns.get(user_id, 0)
        return (now - last) < self.bot.config.GAME_COOLDOWN

    def _set_cooldown(self, user_id: int):
        self._cooldowns[user_id] = time.time()

    async def _validate_bet(self, interaction: discord.Interaction, amount: int) -> bool:
        """Validate bet amount. Returns True if valid."""
        if self._check_cooldown(interaction.user.id):
            await interaction.response.send_message('Кулдаун! Подождите несколько секунд.', ephemeral=True)
            return False

        if amount < self.bot.config.GAME_MIN_BET:
            await interaction.response.send_message(
                f'Минимальная ставка: {self.bot.config.GAME_MIN_BET} монет.', ephemeral=True)
            return False

        balance = await self.bot.user_db.get_money(interaction.user.id)
        if balance < amount:
            await interaction.response.send_message('Недостаточно денег!', ephemeral=True)
            return False

        return True

    async def coinflip(self, interaction: discord.Interaction, amount: int):
        """50/50 coinflip, win x1.8"""
        if not await self._validate_bet(interaction, amount):
            return

        self._set_cooldown(interaction.user.id)
        await interaction.response.defer()

        user_id = interaction.user.id
        won = random.choice([True, False])

        if won:
            winnings = int(amount * 1.8)
            net = winnings - amount
            await self.bot.user_db.add_money(user_id, net)
            new_balance = await self.bot.user_db.get_money(user_id)
            await self.bot.transaction_db.log(user_id, 'coinflip', net, new_balance, 'win')

            embed = discord.Embed(
                title="Монетка - ПОБЕДА!",
                description=f"Вы выиграли **{winnings}** монет! (+{net})\nБаланс: **{new_balance}**",
                color=discord.Color.green()
            )
        else:
            await self.bot.user_db.rem_money(user_id, amount)
            new_balance = await self.bot.user_db.get_money(user_id)
            await self.bot.transaction_db.log(user_id, 'coinflip', -amount, new_balance, 'lose')

            embed = discord.Embed(
                title="Монетка - ПРОИГРЫШ",
                description=f"Вы проиграли **{amount}** монет.\nБаланс: **{new_balance}**",
                color=discord.Color.red()
            )

        await interaction.followup.send(embed=embed)

    async def dice(self, interaction: discord.Interaction, amount: int):
        """Dice roll, player vs bot, win x2, tie returns"""
        if not await self._validate_bet(interaction, amount):
            return

        self._set_cooldown(interaction.user.id)
        await interaction.response.defer()

        user_id = interaction.user.id
        player_roll = random.randint(1, 6)
        bot_roll = random.randint(1, 6)

        embed = discord.Embed(title="Кости")
        embed.add_field(name="Вы", value=str(player_roll), inline=True)
        embed.add_field(name="Бот", value=str(bot_roll), inline=True)

        if player_roll > bot_roll:
            winnings = amount * 2
            net = winnings - amount
            await self.bot.user_db.add_money(user_id, net)
            new_balance = await self.bot.user_db.get_money(user_id)
            await self.bot.transaction_db.log(user_id, 'dice', net, new_balance, f'win {player_roll}v{bot_roll}')
            embed.color = discord.Color.green()
            embed.description = f"Вы выиграли **{winnings}** монет! (+{net})\nБаланс: **{new_balance}**"
        elif player_roll < bot_roll:
            await self.bot.user_db.rem_money(user_id, amount)
            new_balance = await self.bot.user_db.get_money(user_id)
            await self.bot.transaction_db.log(user_id, 'dice', -amount, new_balance, f'lose {player_roll}v{bot_roll}')
            embed.color = discord.Color.red()
            embed.description = f"Вы проиграли **{amount}** монет.\nБаланс: **{new_balance}**"
        else:
            new_balance = await self.bot.user_db.get_money(user_id)
            embed.color = discord.Color.yellow()
            embed.description = f"Ничья! Ставка возвращена.\nБаланс: **{new_balance}**"

        await interaction.followup.send(embed=embed)

    async def duel(self, interaction: discord.Interaction, target: discord.Member, amount: int):
        """Duel another player"""
        if target.id == interaction.user.id:
            await interaction.response.send_message("Нельзя вызвать себя на дуэль!", ephemeral=True)
            return

        if target.bot:
            await interaction.response.send_message("Нельзя вызвать бота на дуэль!", ephemeral=True)
            return

        if not await self._validate_bet(interaction, amount):
            return

        # Check target's balance
        target_balance = await self.bot.user_db.get_money(target.id)
        if target_balance < amount:
            await interaction.response.send_message(
                f"У {target.mention} недостаточно денег!", ephemeral=True)
            return

        view = DuelView(interaction.user, target, amount, self)

        await interaction.response.send_message(
            f"{target.mention}, {interaction.user.mention} вызывает вас на дуэль на **{amount}** монет!",
            view=view
        )

    async def _resolve_duel(self, interaction: discord.Interaction, view: DuelView):
        """Resolve a duel after acceptance"""
        self._set_cooldown(view.challenger.id)
        self._set_cooldown(view.target.id)

        # Re-verify balances
        c_balance = await self.bot.user_db.get_money(view.challenger.id)
        t_balance = await self.bot.user_db.get_money(view.target.id)

        if c_balance < view.amount or t_balance < view.amount:
            await interaction.response.send_message("У одного из игроков недостаточно денег!")
            return

        winner = random.choice([view.challenger, view.target])
        loser = view.target if winner == view.challenger else view.challenger

        await self.bot.user_db.add_money(winner.id, view.amount)
        await self.bot.user_db.rem_money(loser.id, view.amount)

        w_balance = await self.bot.user_db.get_money(winner.id)
        l_balance = await self.bot.user_db.get_money(loser.id)

        await self.bot.transaction_db.log(winner.id, 'duel', view.amount, w_balance,
                                          f'win vs {loser.id}')
        await self.bot.transaction_db.log(loser.id, 'duel', -view.amount, l_balance,
                                          f'lose vs {winner.id}')

        embed = discord.Embed(
            title="Результат дуэли!",
            description=f"{winner.mention} выиграл **{view.amount}** монет у {loser.mention}!",
            color=discord.Color.gold()
        )

        await interaction.response.send_message(embed=embed)
