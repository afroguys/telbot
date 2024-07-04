#!/usr/bin/env python3

import os
import logging
from fnmatch import fnmatch
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext, ConversationHandler, MessageHandler, filters
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

def create_progress_bar(progress, length=20):
    full_block = "█"
    empty_block = "░"
    filled_length = int(length * progress)
    return full_block * filled_length + empty_block * (length - filled_length)

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
        "/list <torrent_name_or_hash> - List files in a torrent\n"
        "/move_specific <file_pattern> <destination_path> - Move specific files matching a pattern\n"
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
            progress_bar = create_progress_bar(torrent['progress'])
            status_message += (
                f"Name: {torrent['name']}\n"
                f"Progress: {torrent['progress']*100:.2f}% [{progress_bar}]\n"
                f"State: {torrent['state']}\n\n"
            )
        
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

@restricted
async def list_files(update: Update, context: CallbackContext) -> None:
    torrent_name_or_hash = ' '.join(context.args)
    if not torrent_name_or_hash:
        await update.message.reply_text('Please provide the name or hash of the torrent to list files.')
        return

    try:
        torrents = qb.torrents_info()
        for torrent in torrents:
            if torrent_name_or_hash in (torrent['name'], torrent['hash']):
                torrent_hash = torrent['hash']
                break
        else:
            await update.message.reply_text('Torrent not found.')
            return

        files = qb.torrents_files(torrent_hash)
        if not files:
            await update.message.reply_text('No files found in the torrent.')
            return

        file_list_message = ""
        for file in files:
            file_list_message += f"{file['name']}\n"

        await update.message.reply_text(f"Files in torrent '{torrent_name_or_hash}':\n\n{file_list_message}")
    except Exception as e:
        await update.message.reply_text(f'An error occurred: {e}')

@restricted
async def move_specific_file(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 2:
        await update.message.reply_text('Usage: /move_specific <file_pattern> <destination_path>')
        return

    file_pattern, destination_path = context.args

    # Verify destination directory exists
    if not os.path.exists(destination_path):
        await update.message.reply_text('Destination path does not exist.')
        return

    try:
        # Find files matching the pattern in all torrents
        torrents = qb.torrents_info()
        moved_files = []
        for torrent in torrents:
            files = qb.torrents_files(torrent['hash'])
            save_path = torrent['save_path']
            for file in files:
                if fnmatch(file['name'], file_pattern):
                    source_path = os.path.join(save_path, file['name'])
                    new_path = os.path.join(destination_path, os.path.basename(file['name']))
                    os.rename(source_path, new_path)
                    moved_files.append(file['name'])

        if not moved_files:
            await update.message.reply_text('No files matching the pattern were found.')
            return

        moved_files_message = "\n".join(moved_files)
        await update.message.reply_text(f"Moved files:\n{moved_files_message}\nto {destination_path}")
    except Exception as e:
        await update.message.reply_text(f'An error occurred: {e}')

# Conversation handler for interactive file move
@restricted
async def move_torrent(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text('What file pattern do you want to move?')
    return SELECT_FILE_PATTERN

@restricted
async def file_pattern_received(update: Update, context: CallbackContext) -> int:
    context.user_data
    ['file_pattern'] = update.message.text
    await update.message.reply_text('Where do you want to move the files? Provide the full destination path.')
    return SELECT_DESTINATION_PATH

@restricted
async def destination_path_received(update: Update, context: CallbackContext) -> int:
    file_pattern = context.user_data.get('file_pattern')
    destination_path = update.message.text

    # Verify destination directory exists
    if not os.path.exists(destination_path):
        await update.message.reply_text('Destination path does not exist.')
        return ConversationHandler.END

    try:
        # Find files matching the pattern in all torrents
        torrents = qb.torrents_info()
        moved_files = []
        for torrent in torrents:
            files = qb.torrents_files(torrent['hash'])
            save_path = torrent['save_path']
            for file in files:
                if fnmatch(file['name'], file_pattern):
                    source_path = os.path.join(save_path, file['name'])
                    new_path = os.path.join(destination_path, os.path.basename(file['name']))
                    os.rename(source_path, new_path)
                    moved_files.append(file['name'])

        if not moved_files:
            await update.message.reply_text('No files matching the pattern were found.')
            return ConversationHandler.END

        moved_files_message = "\n".join(moved_files)
        await update.message.reply_text(f"Moved files:\n{moved_files_message}\nto {destination_path}")
    except Exception as e:
        await update.message.reply_text(f'An error occurred: {e}')

    return ConversationHandler.END

async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text('Operation cancelled.')
    return ConversationHandler.END

def main() -> None:
    # Set up the Application
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Define conversation handler for moving files interactively
    move_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('move', move_torrent)],
        states={
            SELECT_FILE_PATTERN: [MessageHandler(Filters.text & ~Filters.command, file_pattern_received)],
            SELECT_DESTINATION_PATH: [MessageHandler(Filters.text & ~Filters.command, destination_path_received)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # Add handlers to the application
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", add_torrent))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("remove", remove_torrent))
    application.add_handler(CommandHandler("list", list_files))
    application.add_handler(CommandHandler("move_specific", move_specific_file))
    application.add_handler(move_conv_handler)

    # Start the Bot
    application.run_polling()

if __name__ == '__main__':
    main()
