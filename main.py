import asyncio
import ssl
import certifi
from src.bot import DiscordBot

# Fix SSL certificates on macOS
ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())

async def main():
    bot = DiscordBot()
    bot.config.validate()
    await bot.run_bot()

if __name__ == "__main__":
    asyncio.run(main())
