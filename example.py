import logging

from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

TOKEN = ''

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
updater = Updater(token=TOKEN)

dispatcher = updater.dispatcher


def start(bot, update):
    bot.send_message(chat_id=update.message.chat_id,
                     text='Im a bot!!')


def echo(bot, update):
    bot.send_message(chat_id=update.message.chat_id,
                     text=update.message.text)


def caps(bot, update, args):
    text_caps = ' '.join(args).upper()
    bot.send_message(chat_id=update.message.chat_id,
                     text=text_caps)

echo_handler = MessageHandler(Filters.all, echo)
start_handler = CommandHandler('start', start)
caps_handler = CommandHandler('caps', caps, pass_args=True)
dispatcher.add_handler(start_handler)
dispatcher.add_handler(echo_handler, group=0)
dispatcher.add_handler(caps_handler)

updater.start_polling()


