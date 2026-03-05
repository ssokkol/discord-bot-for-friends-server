import os
import requests
from PIL import Image, ImageDraw, ImageOps, ImageFont
from typing import Optional
from io import BytesIO
import logging

logger = logging.getLogger(__name__)


class ProfileImageGenerator:
    """Profile image generator for the Discord bot"""

    def __init__(self, assets_path: str = "assets"):
        self.assets_path = assets_path
        self.font_path = os.path.join(assets_path, "fonts", "AB.otf")

        self.templates = {
            'online': os.path.join(assets_path, 'templates', 'otemplate.png'),
            'idle': os.path.join(assets_path, 'templates', 'itemplate.png'),
            'dnd': os.path.join(assets_path, 'templates', 'dnttemplate.png'),
            'offline': os.path.join(assets_path, 'templates', 'offtemplate.png')
        }

        self.default_avatar = os.path.join(assets_path, 'avatars', 'avatar.jpg')
        self.backgrounds_path = os.path.join(assets_path, 'backgrounds')

    async def download_avatar(self, avatar_url: str) -> Optional[Image.Image]:
        """Download user avatar"""
        try:
            response = requests.get(avatar_url, timeout=10)
            response.raise_for_status()
            img_data = response.content
            img = Image.open(BytesIO(img_data)).convert("RGBA")
            return img
        except Exception as e:
            logger.error(f"Error downloading avatar: {e}")
            return None

    def create_circular_avatar(self, avatar: Image.Image, size: tuple) -> Image.Image:
        """Create a circular avatar"""
        try:
            avatar = avatar.resize(size)
            bigsize = (avatar.size[0] * 3, avatar.size[1] * 3)
            mask = Image.new('L', bigsize, 0)
            draw = ImageDraw.Draw(mask)
            draw.ellipse((0, 0) + bigsize, fill=255)
            mask = mask.resize(avatar.size, Image.Resampling.LANCZOS)
            avatar.putalpha(mask)
            return avatar
        except Exception as e:
            logger.error(f"Error creating circular avatar: {e}")
            return avatar

    def add_text_to_image(self, img: Image.Image, text: str, position: tuple,
                          font_size: int = 64, color: tuple = (255, 255, 255)) -> Image.Image:
        """Add text to image"""
        try:
            draw = ImageDraw.Draw(img)
            font = ImageFont.truetype(self.font_path, font_size)
            draw.text(position, text, font=font, fill=color)
        except Exception as e:
            logger.error(f"Error adding text: {e}")
        return img

    def truncate_text(self, text: str, max_length: int) -> str:
        if len(text) > max_length:
            return text[:max_length-3] + "..."
        return text

    def _draw_xp_bar(self, img: Image.Image, xp: int, xp_needed: int, level: int,
                     position: tuple = (91, 1040), size: tuple = (800, 30)):
        """Draw an XP progress bar with gradient fill"""
        try:
            draw = ImageDraw.Draw(img)
            x, y = position
            w, h = size
            radius = h // 2

            # Background (dark rounded rect)
            draw.rounded_rectangle(
                [x, y, x + w, y + h],
                radius=radius,
                fill=(40, 40, 40, 200)
            )

            # Progress fill
            progress = xp / xp_needed if xp_needed > 0 else 0
            fill_width = max(int(w * progress), radius * 2) if progress > 0 else 0

            if fill_width > 0:
                # Gradient from blue to purple
                for i in range(fill_width):
                    ratio = i / max(w, 1)
                    r = int(66 + (155 - 66) * ratio)
                    g = int(133 + (89 - 133) * ratio)
                    b = int(244 + (182 - 244) * ratio)
                    draw.line([(x + i, y + 1), (x + i, y + h - 1)], fill=(r, g, b))

                # Re-draw rounded corners by masking
                mask = Image.new('L', img.size, 255)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.rounded_rectangle(
                    [x, y, x + w, y + h],
                    radius=radius,
                    fill=255
                )
                # Apply mask to clip the gradient within rounded rect
                # (simplified - just overdraw the outer area)
                draw.rounded_rectangle(
                    [x + fill_width, y, x + w, y + h],
                    radius=radius,
                    fill=(40, 40, 40, 200)
                )

            # Level text
            font = ImageFont.truetype(self.font_path, 24)
            level_text = f"LVL {level}"
            draw.text((x + 5, y + 2), level_text, font=font, fill=(255, 255, 255))

            # XP text (right-aligned)
            xp_text = f"{xp}/{xp_needed} XP"
            bbox = draw.textbbox((0, 0), xp_text, font=font)
            text_width = bbox[2] - bbox[0]
            draw.text((x + w - text_width - 5, y + 2), xp_text, font=font, fill=(255, 255, 255))

        except Exception as e:
            logger.error(f"Error drawing XP bar: {e}")

    async def generate_profile_image(self, user_data: dict, output_path: str = "output.png") -> bool:
        """Generate profile image"""
        try:
            status = str(user_data.get('status', 'online')).lower()
            status_mapping = {
                'online': 'otemplate.png',
                'idle': 'itemplate.png',
                'dnd': 'dnttemplate.png',
                'offline': 'offtemplate.png'
            }

            # Check for custom background first
            custom_bg = user_data.get('custom_background')
            if custom_bg:
                bg_path = os.path.join(self.backgrounds_path, custom_bg)
                if os.path.exists(bg_path):
                    background = Image.open(bg_path).convert("RGBA")
                else:
                    custom_bg = None

            if not custom_bg:
                template_name = status_mapping.get(status, 'otemplate.png')
                template_path = os.path.join(self.assets_path, 'templates', template_name)

                if not os.path.exists(template_path):
                    logger.error(f"Template not found: {template_path}")
                    return False

                background = Image.open(template_path)

            # Avatar
            avatar_url = user_data.get('avatar_url')
            if avatar_url:
                avatar = await self.download_avatar(avatar_url)
                if avatar:
                    circular_avatar = self.create_circular_avatar(avatar, (238, 238))
                    background.paste(circular_avatar, (70, 158), circular_avatar)

            img = background

            # Nickname
            nick = self.truncate_text(user_data.get('nickname', ''), 12)
            img = self.add_text_to_image(img, nick, (344, 207), 100)

            # Dates
            dates = f"{user_data.get('created_date', '')}/{user_data.get('joined_date', '')}"
            dates = self.truncate_text(dates, 21)
            img = self.add_text_to_image(img, dates, (135, 448), 40)

            # Balance
            balance = f"{user_data.get('balance', 0)} руб"
            balance = self.truncate_text(balance, 26)
            img = self.add_text_to_image(img, balance, (91, 667), 64)

            # Messages
            messages = f"{user_data.get('messages', 0)} сообщений"
            messages = self.truncate_text(messages, 27)
            img = self.add_text_to_image(img, messages, (91, 793), 64)

            # Voice time
            voice_time = f"{user_data.get('voice_time', '0:00:00')} в войсе"
            voice_time = self.truncate_text(voice_time, 28)
            img = self.add_text_to_image(img, voice_time, (91, 918), 64)

            # Level/XP bar
            level = user_data.get('level', 0)
            xp = user_data.get('xp', 0)
            xp_needed = user_data.get('xp_needed', 100)
            self._draw_xp_bar(img, xp, xp_needed, level)

            img.save(output_path, optimize=True, quality=95)
            return True

        except Exception as e:
            logger.error(f"Error generating image: {e}")
            return False

    async def add_badges_to_profile(self, profile_path: str, user_roles: list,
                                   badges_path: str = "assets/badges") -> bool:
        """Add badges to profile image"""
        try:
            if not os.path.exists(profile_path):
                logger.error(f"Profile file not found: {profile_path}")
                return False

            img = Image.open(profile_path)

            for role_id in user_roles:
                badge_path = os.path.join(badges_path, f"{role_id}.png")

                if os.path.exists(badge_path):
                    try:
                        badge = Image.open(badge_path)
                        img2 = Image.new("RGBA", img.size)
                        img2 = Image.alpha_composite(img2, img)
                        img2 = Image.alpha_composite(img2, badge)
                        img2.save(profile_path, optimize=True, quality=95)
                        img = img2
                    except Exception as e:
                        logger.warning(f"Could not add badge {role_id}: {e}")
                        continue

            return True

        except Exception as e:
            logger.error(f"Error adding badges: {e}")
            return False
