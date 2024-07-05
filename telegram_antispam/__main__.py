# -*- coding=utf-8 -*-
from datetime import datetime, timedelta, UTC
import functools
import logging
import os

from telegram import BotCommandScopeAllPrivateChats, Update
from telegram.ext import (Application, ChatMemberHandler, CommandHandler, ContextTypes, filters, MessageHandler,
                          PicklePersistence)

logger = logging.getLogger(__name__)

DATA_PATH = os.environ["DATA_PATH"]
TOKEN = os.environ["TOKEN"]


async def chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_member = update.chat_member

    if chat_member.new_chat_member.status == "member" and chat_member.old_chat_member.status in ["left", "kicked"]:
        logger.debug(
            f"Chat {update.chat_member.chat.id} ({update.chat_member.chat.title!r}): "
            f"user {chat_member.new_chat_member.user.id} ({chat_member.new_chat_member.user.name!r}) joined"
        )

        context.chat_data.setdefault("user_joined_at", {})
        context.chat_data["user_joined_at"][chat_member.new_chat_member.user.id] = datetime.now(UTC)


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_prefix = (f"Chat {update.message.chat.id} ({update.message.chat.title!r}): "
                  f"user {update.message.from_user.id} ({update.message.from_user.name!r})")

    user_joined_at = context.chat_data.get("user_joined_at", {}).get(update.message.from_user.id)
    if user_joined_at is None:
        logger.debug(f"{log_prefix}: user has no join timestamp. Assuming now")

        context.chat_data.setdefault("user_joined_at", {})
        user_joined_at = context.chat_data[update.message.from_user.id] = datetime.now(UTC)

    if user_joined_at < datetime.now(UTC) - timedelta(days=1):
        logger.debug(f"{log_prefix}: new message from trusted user (joined at {user_joined_at})")
        return

    context.chat_data.setdefault("user_message_count", {})
    message_count = context.chat_data["user_message_count"].setdefault(update.message.from_user.id, 0)
    if message_count >= 3:
        logger.debug(f"{log_prefix}: new message from trusted user (has >= {message_count} messages)")
        return

    logger.debug(f"{log_prefix}: new message from unfamiliar user (joined at {user_joined_at}, "
                 f"has {message_count} messages)")
    words = context.bot_data.get("words", set())
    for word in words:
        if word in update.message.text.lower():
            logger.info(f"{log_prefix}: message ({update.message.text!r}) contains a prohibited word ({word!r})")

            owner_id = context.bot_data.get("owner_id")
            if owner_id is None:
                logger.warning("The bot does not have an owner")
            else:
                await context.bot.send_message(
                    chat_id=owner_id,
                    text=(f"The following message:\n\n{update.message.text}\n\n"
                          f"by user {update.message.from_user.name} "
                          f"was deleted in the group {update.message.chat.title!r}")
                )

            await update.message.delete()
            await context.bot.ban_chat_member(update.effective_chat.id, user_id=update.message.from_user.id)
            return

    context.chat_data["user_message_count"][update.message.from_user.id] = message_count + 1


def admin_command(func):
    @functools.wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if (owner_id := context.bot_data.get("owner_id")) is None:
            owner_id = context.bot_data["owner_id"] = update.message.from_user.id
            await update.message.reply_text("You are now the owner of the bot.")

        if update.message.from_user.id != owner_id:
            await update.message.reply_text("You are not the owner of the bot.")
            return

        return await func(update, context)

    return wrapped


@admin_command
async def list_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    words = context.bot_data.get("words", set())
    if not words:
        await update.message.reply_text("No prohibited words.")
        return

    words_list = "\n".join(sorted(words))
    await update.message.reply_text(f"Prohibited words:\n{words_list}")


@admin_command
async def add_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /add <word>")
        return

    word = context.args[0].lower()

    context.bot_data.setdefault("words", set())
    context.bot_data["words"].add(word)

    await update.message.reply_text(f"Added prohibited word: {word}")


@admin_command
async def delete_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /delete <word>")
        return

    word = context.args[0].lower()

    context.bot_data.setdefault("words", set())
    context.bot_data["words"].discard(word)

    await update.message.reply_text(f"Deleted prohibited word: {word}")


async def post_init(application: Application):
    await application.bot.set_my_commands([
        ("list", "List of prohibited words"),
        ("add", "Add a prohibited word"),
        ("delete", "Delete a prohibited word"),
    ], scope=BotCommandScopeAllPrivateChats())


def main():
    application = (
        Application.
        builder().
        token(TOKEN).
        persistence(PicklePersistence(DATA_PATH)).
        post_init(post_init).
        build()
    )

    application.add_handler(ChatMemberHandler(chat_member_handler, ChatMemberHandler.CHAT_MEMBER))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    application.add_handler(CommandHandler("list", list_command_handler))
    application.add_handler(CommandHandler("add", add_command_handler))
    application.add_handler(CommandHandler("delete", delete_command_handler))

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="[%(asctime)s] %(levelname)-8s [%(name)s] %(message)s")
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)

    main()
