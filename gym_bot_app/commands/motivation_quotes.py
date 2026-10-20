from telegram import Update
from telegram.ext import CallbackContext

from gym_bot_app.decorators import get_trainee_and_group
from gym_bot_app.commands import Command
from gym_bot_app.quotes import format_quote, random_quote

from gym_bot_app.models import Trainee, Group


class MotivationQuotesCommand(Command):
    """Telegram gym bot motivation me command.

    Sends training motivation quote.

    """

    DEFAULT_COMMAND_NAME = 'motivate_me'

    def __init__(self, *args, **kwargs):
        super(MotivationQuotesCommand, self).__init__(*args, **kwargs)

    @get_trainee_and_group
    def _handler(self, update: Update, context: CallbackContext, trainee: Trainee, group: Group):
        """Override method to handle motivation quote command.

        Sends a random quote back to the chat.

        """
        self.logger.info('%s asked to be motivated in %s', trainee, group)

        update.message.reply_text(quote=True,
                                  text=format_quote(random_quote()))
