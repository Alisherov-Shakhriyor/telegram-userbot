import asyncio
import json
import logging
import os
import random
import sys
from pathlib import Path

from telethon import TelegramClient, events
from telethon.errors import RPCError
from telethon.tl.types import User


# Configuration
SESSION_FILE = "userbot.session"
REPLIED_STORE = Path("replied_users.json")

DEFAULT_REPLY = os.getenv(
    "AUTO_REPLY_TEXT",
    "Rahmat, xabaringizni oldim. Tez orada qaytib yozaman."
)

REPLY_CATEGORIES = [
    {
        "name": "greeting",
        "patterns": ["salom", "assalomu", "assalom", "hello", "hi", "hey", "qalesiz", "yahshi"],
        "env_key": "AUTO_REPLY_GREETING_TEXT",
        "default": "Salom! Xabaringiz uchun rahmat. Tez orada javob beraman."
    },
    {
        "name": "price",
        "patterns": ["narx", "cost", "price", "price list", "pricing", "qanchalik", "necha", "qancha", "quote"],
        "env_key": "AUTO_REPLY_PRICE_TEXT",
        "default": "Narx haqida so'raganingiz uchun rahmat. Iltimos, kerakli ma'lumotni yuboring, men javob beraman."
    },
    {
        "name": "thanks",
        "patterns": ["rahmat", "thank you", "thanks", "olcham", "yaxshi"],
        "env_key": "AUTO_REPLY_THANKS_TEXT",
        "default": "Sizga yordam bera olganimdan xursandman! Yana savolingiz bo'lsa, yozing."
    },
    {
        "name": "help",
        "patterns": ["yordam", "help", "qanday", "nima qilasan", "qanaqa"],
        "env_key": "AUTO_REPLY_HELP_TEXT",
        "default": "Men sizning xabaringizni oldim. Yordam kerak bo'lsa, aniqroq savol bering."
    },
    {
        "name": "contact",
        "patterns": ["aloqa", "telefon", "raqam", "kontakt", "how to contact"],
        "env_key": "AUTO_REPLY_CONTACT_TEXT",
        "default": "Aloqa uchun javob: iltimos, talab va savolingizni yozing, tez orada aloqaga chiqaman."
    }
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_dotenv(dotenv_path: Path = Path(".env")) -> None:
    if not dotenv_path.exists():
        return

    try:
        with dotenv_path.open("r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue

                if "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
        logger.info("Loaded environment variables from %s", dotenv_path)
    except OSError as exc:
        logger.warning("Could not read .env file: %s", exc)


def load_replied_users() -> dict[str, set[str]]:
    if not REPLIED_STORE.exists():
        return {}

    try:
        with REPLIED_STORE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return {str(user_id): set(categories or []) for user_id, categories in data.items()}
            return {}
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not load replied users file: %s", exc)
        return {}


def save_replied_users(replied: dict[str, set[str]]) -> None:
    try:
        with REPLIED_STORE.open("w", encoding="utf-8") as f:
            json.dump({user_id: sorted(list(categories)) for user_id, categories in replied.items()}, f, indent=2, ensure_ascii=False)
    except OSError as exc:
        logger.error("Failed to save replied users file: %s", exc)


def get_reply_info(message_text: str) -> tuple[str, str]:
    normalized = message_text.lower()
    for category in REPLY_CATEGORIES:
        if any(pattern in normalized for pattern in category["patterns"]):
            reply_text = os.getenv(category["env_key"], category["default"])
            return category["name"], reply_text
    return "default", DEFAULT_REPLY


async def main() -> None:
    load_dotenv()

    api_id_value = os.getenv("API_ID")
    api_hash_value = os.getenv("API_HASH")

    missing = []
    if not api_id_value:
        missing.append("API_ID")
    if not api_hash_value:
        missing.append("API_HASH")

    if missing:
        logger.error(
            "Missing environment variables: %s.\n"
            "Use a .env file or set them in PowerShell before running:\n"
            "$env:API_ID = '35722060'\n"
            "$env:API_HASH = 'd71b8bf19eaf092909d8461071ef3883'\n"
            "python main.py",
            ", ".join(missing),
        )
        sys.exit(1)

    try:
        api_id = int(api_id_value)
    except ValueError:
        logger.error("API_ID must be an integer. Got: %r", api_id_value)
        sys.exit(1)

    client = TelegramClient(SESSION_FILE, api_id, api_hash_value)
    replied_users = load_replied_users()

    await client.start()
    me = await client.get_me()
    logger.info("Logged in as %s (%s)", getattr(me, 'username', 'unknown'), me.id)

    @client.on(events.NewMessage(incoming=True))
    async def on_private_message(event: events.NewMessage.Event) -> None:
        try:
            if not event.is_private:
                return

            if event.out:
                return

            sender = await event.get_sender()
            if not isinstance(sender, User):
                return

            if sender.bot:
                logger.info("Ignored bot message from %s (%s)", sender.username or sender.id, sender.id)
                return

            if sender.id == me.id:
                logger.info("Ignored message from self.")
                return

            user_key = str(sender.id)
            text = event.raw_text or ""
            category, reply_message = get_reply_info(text)
            categories = replied_users.get(user_key, set())

            if category in categories:
                logger.info(
                    "Already replied to %s (%s) for category=%s. Skipping.",
                    sender.username or sender.id,
                    sender.id,
                    category,
                )
                return

            delay = random.uniform(3, 5)
            logger.info(
                "Received private message from %s (%s) at %s. Replying after %.2f seconds.",
                sender.username or sender.id,
                sender.id,
                event.date,
                delay,
            )
            await asyncio.sleep(delay)
            await event.respond(reply_message)
            replied_users.setdefault(user_key, set()).add(category)
            save_replied_users(replied_users)
            logger.info(
                "Auto-replied to %s (%s) category=%s.",
                sender.username or sender.id,
                sender.id,
                category,
            )

        except RPCError as exc:
            logger.error("Telegram RPC error while handling message: %s", exc)
        except Exception as exc:
            logger.exception("Unhandled error while processing message: %s", exc)

    logger.info("Userbot is running and listening for private messages...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopping userbot.")
