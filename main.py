#!/usr/bin/env python3

import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext
import qbittorrentapi
from config import TELEGRAM_TOKEN, ALLOWED_USERS, QBITTORRENT_HOST, QBITTORRENT_USERNAME, QBITTORRENT_PASSWORD

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize qBittorrent client
qb = qbittorrentapi.Client(host=QBITTORRENT_HOST, username=QBITTORRENT_USERNAME, password=QBITTORRENT_PASSWORD)

try:
    qb.auth_log_in()
except qbittorrentapi.LoginFailed as e:
    logger.error(f"Failed to log in to qBittorrent: {e}")

# Security decorator
def restricted(func):
    async def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in ALLOWED_USERS:
            await update.message.reply_text("You are not authorized to use this bot.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# Define the commands
@restricted
async def start(update: Update, context: CallbackContext) -> None:
    motd = (
        "Welcome to the Telegram Torrent Bot!\n\n"
        "Here are the available commands:\n"
        "/start - Display this message\n"
        "/add <magnet_link> - Add a torrent\n"
        "/move <source_path> <destination_path> - Move a file\n"
        "/status - Show the status of active torrents\n"
        "/remove <torrent_name_or_hash> - Remove a torrent\n"
    )
    await update.message.reply_text(motd)

@restricted
async def add_torrent(update: Update, context: CallbackContext) -> None:
    magnet_link = ' '.join(context.args)
    if not magnet_link:
        await update.message.reply_text('Please provide a magnet link or torrent URL.')
        return

    try:
        qb.torrents_add(urls=magnet_link)
        await update.message.reply_text('Torrent added successfully!')
    except qbittorrentapi.APIConnectionError:
        await update.message.reply_text('Failed to connect to qBittorrent. Ensure it is running.')
    except Exception as e:
        await update.message.reply_text(f'An error occurred: {e}')

@restricted
async def move_file(update: Update, context: CallbackContext) -> None:
    args = context.args
    if len(args) != 2:
        await update.message.reply_text('Usage: /move <source_path> <destination_path>')
        return

    source_path, destination_path = args
    try:
        os.rename(source_path, destination_path)
        await update.message.reply_text(f'File moved from {source_path} to {destination_path}')
    except Exception as e:
        await update.message.reply_text(f'Error: {e}')

@restricted
async def status(update: Update, context: CallbackContext) -> None:
    try:
        torrents = qb.torrents_info()
        if not torrents:
            await update.message.reply_text('No active torrents.')
            return
        
        status_message = ""
        for torrent in torrents:
            status_message += f"Name: {torrent['name']}\nProgress: {torrent['progress']*100:.2f}%\nState: {torrent['state']}\n\n"
        
        await update.message.reply_text(status_message)
    except Exception as e:
        await update.message.reply_text(f'An error occurred: {e}')

@restricted
async def remove_torrent(update: Update, context: CallbackContext) -> None:
    torrent_name_or_hash = ' '.join(context.args)
    if not torrent_name_or_hash:
        await update.message.reply_text('Please provide the name or hash of the torrent to remove.')
        return

    try:
        torrents = qb.torrents_info()
        for torrent in torrents:
            if torrent_name_or_hash in (torrent['name'], torrent['hash']):
                qb.torrents_delete(delete_files=True, torrent_hashes=torrent['hash'])
                await update.message.reply_text(f"Torrent '{torrent['name']}' removed successfully.")
                return
        await update.message.reply_text('Torrent not found.')
    except qbittorrentapi.APIConnectionError:
        await update.message.reply_text('Failed to connect to qBittorrent. Ensure it is running.')
    except Exception as e:
        await update.message.reply_text(f'An error occurred: {e}')

def main() -> None:
    # Set up the Application
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", add_torrent))
    application.add_handler(CommandHandler("move", move_file))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("remove", remove_torrent))

    # Start the Bot
    application.run_polling()

if __name__ == '__main__':
    main()
