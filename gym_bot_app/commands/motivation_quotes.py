from telegram import Update
from telegram.ext import CallbackContext

from gym_bot_app.decorators import get_trainee_and_group
from gym_bot_app.commands import Command
import textwrap
import random

from gym_bot_app.models import Trainee, Group


class MotivationQuotesCommand(Command):
    """Telegram gym bot motivation me command.

    Sends training motivation quote.

    """
    
    DEFAULT_COMMAND_NAME = 'motivate_me'

    QUOTE_MSG = '"{text}", {author}'
    
    QUOTE_LIST = [
        {'text': 'The last three or four reps is what makes the muscle grow. This area of pain divides a champion from someone who is not a champion.', 'author': 'Arnold Schwarzenegger'},
        {'text': 'Success usually comes to those who are too busy to be looking for it.', 'author': 'Henry David Thoreau'},
        {'text': 'All progress takes place outside the comfort zone', 'author': 'Michael John Bobak'},
        {'text': 'If you think lifting is dangerous, try being weak. Being weak is dangerous.', 'author': 'Bret Contreras'},
        {'text': 'The only place where success comes before work is in the dictionary.', 'author': 'Vidal Sassoon'},
        {'text': 'The clock is ticking. Are you becoming the person you want to be?', 'author': 'Greg Plitt'},
        {'text': 'Whether you think you can, or you think you can’t, you’re right.', 'author': 'Henry Ford'},
        {'text': 'The successful warrior is the average man, with laser-like focus.', 'author': 'Bruce Lee'},
        {'text': 'You must expect great things of yourself before you can do them.', 'author': 'Michael Jordan'},
        {'text': 'Action is the foundational key to all success.', 'author': 'Pablo Picasso'},
        {'text': 'Everyone is a bot', 'author': 'Asaf sh'},
    ]

    def __init__(self, *args, **kwargs):
        super(MotivationQuotesCommand, self).__init__(*args, **kwargs)

    @get_trainee_and_group
    def _handler(self, update: Update, context: CallbackContext, trainee: Trainee, group: Group):
        """Override method to handle motivation quote command.

        Randomize a number between 0 and the number of quotes -1 and send quote
         in this index back to the chat.

        """
        self.logger.info('%s asked to be motivated in %s', trainee, group)

        random_number = random.randint(0, len(self.QUOTE_LIST) - 1)
        random_quote = self.QUOTE_LIST[random_number]

        quote_text = self.QUOTE_MSG.format(
            text=random_quote['text'],
            author=random_quote['author']
        )
        update.message.reply_text(quote=True,
                                  text=quote_text)
