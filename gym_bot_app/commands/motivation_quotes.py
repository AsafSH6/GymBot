import random

from telegram import Update
from telegram.ext import CallbackContext

from gym_bot_app.decorators import get_trainee_and_group
from gym_bot_app.commands import Command
from gym_bot_app.quotes import QUOTE_LIST, format_quote

from gym_bot_app.models import PersonalMotivationQuote, Trainee, Group


class MotivationQuotesCommand(Command):
    """Telegram gym bot motivation me command.

    Sends training motivation quote, picked from the quotes list and the motivation
    sentences the trainees of the group set (see SetMotivationCommand).

    """

    DEFAULT_COMMAND_NAME = 'motivate_me'

    PERSONAL_QUOTE_WEIGHT = 3  # Each personal quote is this many times as likely to be picked as a quote of the list.

    def __init__(self, *args, **kwargs):
        super(MotivationQuotesCommand, self).__init__(*args, **kwargs)

    @get_trainee_and_group
    def _handler(self, update: Update, context: CallbackContext, trainee: Trainee, group: Group):
        """Override method to handle motivation quote command.

        Pick a random quote out of the quotes list and the personal motivation quotes
         of the group, favoring the personal ones by PERSONAL_QUOTE_WEIGHT, and send it back to the chat.

        """
        self.logger.info('%s asked to be motivated in %s', trainee, group)

        personal_quotes = list(PersonalMotivationQuote.objects(group=group.pk))
        weights = [1] * len(QUOTE_LIST) + [self.PERSONAL_QUOTE_WEIGHT] * len(personal_quotes)
        quote, = random.choices(QUOTE_LIST + personal_quotes, weights=weights)

        if isinstance(quote, PersonalMotivationQuote):
            quote = quote.as_quote()

        update.message.reply_text(quote=True,
                                  text=format_quote(quote),
                                  disable_web_page_preview=True)
