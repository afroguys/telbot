import os
import logging
import fnmatch
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext, MessageHandler, Filters, ConversationHandler
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
    def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in ALLOWED_USERS:
            update.message.reply_text("You are not authorized to use this bot.")
            return
        return func(update, context, *args, **kwargs)
    return wrapped

# Define states for conversation handler
SELECT_FILE_PATTERN, SELECT_DESTINATION = range(2)

def create_progress_bar(progress, length=20):
    full_block = "█"
    empty_block = "░"
    filled_length = int(length * progress)
    return full_block * filled_length + empty_block * (length - filled_length)

@restricted
def start(update: Update, context: CallbackContext) -> None:
    motd = (
        "Welcome to the Telegram Torrent Bot!\n\n"
        "Here are the available commands:\n"
        "/start - Display this message\n"
        "/add <magnet_link> - Add a torrent\n"
        "/move <torrent_name> - Move a file\n"
        "/status - Show the status of active torrents\n"
        "/remove <torrent_name_or_hash> - Remove a torrent\n"
        "/list <torrent_name_or_hash> - List files in a torrent\n"
    )
    update.message.reply_text(motd)

@restricted
def add_torrent(update: Update, context: CallbackContext) -> None:
    magnet_link = ' '.join(context.args)
    if not magnet_link:
        update.message.reply_text('Please provide a magnet link or torrent URL.')
        return

    try:
        qb.torrents_add(urls=magnet_link)
        update.message.reply_text('Torrent added successfully!')
    except qbittorrentapi.APIConnectionError:
        update.message.reply_text('Failed to connect to qBittorrent. Ensure it is running.')
    except Exception as e:
        update.message.reply_text(f'An error occurred: {e}')

@restricted
def status(update: Update, context: CallbackContext) -> None:
    try:
        torrents = qb.torrents_info()
        if not torrents:
            update.message.reply_text('No active torrents.')
            return
        
        status_message = ""
        for torrent in torrents:
            progress_bar = create_progress_bar(torrent.progress)
            status_message += (
                f"Name: {torrent.name}\n"
                f"Progress: {torrent.progress * 100:.2f}% {progress_bar}\n"
                f"State: {torrent.state}\n\n"
            )
        
        update.message.reply_text(status_message)
    except Exception as e:
        update.message.reply_text(f'An error occurred: {e}')

@restricted
def remove_torrent(update: Update, context: CallbackContext) -> None:
    torrent_name_or_hash = ' '.join(context.args)
    if not torrent_name_or_hash:
        update.message.reply_text('Please provide the name or hash of the torrent to remove.')
        return

    try:
        torrents = qb.torrents_info()
        for torrent in torrents:
            if torrent_name_or_hash in (torrent.name, torrent.hash):
                qb.torrents_delete(delete_files=True, torrent_hashes=torrent.hash)
                update.message.reply_text(f"Torrent '{torrent.name}' removed successfully.")
                return
        update.message.reply_text('Torrent not found.')
    except qbittorrentapi.APIConnectionError:
        update.message.reply_text('Failed to connect to qBittorrent. Ensure it is running.')
    except Exception as e:
        update.message.reply_text(f'An error occurred: {e}')

@restricted
def list_files(update: Update, context: CallbackContext) -> None:
    torrent_name_or_hash = ' '.join(context.args)
    if not torrent_name_or_hash:
        update.message.reply_text('Please provide the name or hash of the torrent to list files.')
        return

    try:
        torrents = qb.torrents_info()
        for torrent in torrents:
            if torrent_name_or_hash in (torrent.name, torrent.hash):
                files = qb.torrents_files(torrent_hash=torrent.hash)
                file_list = '\n'.join([file.name for file in files])
                update.message.reply_text(f"Files in '{torrent.name}':\n{file_list}")
                return
        update.message.reply_text('Torrent not found.')
    except qbittorrentapi.APIConnectionError:
        update.message.reply_text('Failed to connect to qBittorrent. Ensure it is running.')
    except Exception as e:
        update.message.reply_text(f'An error occurred: {e}')

@restricted
def move_torrent(update: Update, context: CallbackContext) -> int:
    torrent_name = ' '.join(context.args)
    if not torrent_name:
        update.message.reply_text('Please provide the name of the torrent to move files from.')
        return ConversationHandler.END

    context.user_data['torrent_name'] = torrent_name
    update.message.reply_text('Please provide the file pattern to move (e.g., *.mkv):')
    return SELECT_FILE_PATTERN

def file_pattern_received(update: Update, context: CallbackContext) -> int:
    context.user_data['file_pattern'] = update.message.text
    update.message.reply_text('Please provide the destination folder:')
    return SELECT_DESTINATION

def destination_received(update: Update, context: CallbackContext) -> int:
    destination_path = update.message.text
    file_pattern = context.user_data['file_pattern']
    torrent_name = context.user_data['torrent_name']

    try:
        torrents = qb.torrents_info()
        for torrent in torrents:
            if torrent_name == torrent.name:
                files = qb.torrents_files(torrent_hash=torrent.hash)
                for file in files:
                    if fnmatch.fnmatch(file.name, file_pattern):
                        source_path = os.path.join('/path/to/torrent/downloads', file.name)
                        os.rename(source_path, os.path.join(destination_path, os.path.basename(file.name)))
                        update.message.reply_text(f'Moved {file.name} to {destination_path}')
                return ConversationHandler.END
        update.message.reply_text('Torrent not found.')
    except qbittorrentapi.APIConnectionError:
        update.message.reply_text('Failed to connect to qBittorrent. Ensure it is running.')
    except Exception as e:
        update.message.reply_text(f'An error occurred: {e}')
    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text('Operation cancelled.')
    return ConversationHandler.END

def main() -> None:
    # Set up the Updater
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    # Add command handlers
    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(CommandHandler('add', add_torrent))
    dispatcher.add_handler(CommandHandler('status', status))
    dispatcher.add_handler(CommandHandler('remove', remove_torrent))
    dispatcher.add_handler(CommandHandler('list', list_files))

    # Add conversation handler for moving files
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('move', move_torrent)],
        states={
            SELECT_FILE_PATTERN: [MessageHandler(Filters.text & ~Filters.command, file_pattern_received)],
            SELECT_DESTINATION: [MessageHandler(Filters.text & ~Filters.command, destination_received)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    dispatcher.add_handler(conv_handler)

    # Start the bot
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
