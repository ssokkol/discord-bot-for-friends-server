import asyncio
from src.bot import DiscordBot

async def main():
    bot = DiscordBot()
    bot.config.validate()
    await bot.run_bot()

if __name__ == "__main__":
    asyncio.run(main())
