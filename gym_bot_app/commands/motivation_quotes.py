# encoding: utf-8
from __future__ import unicode_literals

from gym_bot_app.decorators import get_trainee_and_group
from gym_bot_app.commands import Command
import textwrap
import random

class MotivationQuotesCommand(Command):
    """Telegram gym bot motivation me command.

    Sends training motivation quote.

    """
    
    DEFAULT_COMMAND_NAME = 'motivate_me'

    QUOTE_MSG = textwrap.dedent('"{text}", {auther}')
    
    QUOTE_LIST = [
        {'text': 'The last three or four reps is what makes the muscle grow. This area of pain divides a champion from someone who is not a champion.', 'auther': 'Arnold Schwarzenegger'},
        {'text': 'Success usually comes to those who are too busy to be looking for it.', 'auther': 'Henry David Thoreau'},
        {'text': 'All progress takes place outside the comfort zone', 'auther': 'Michael John Bobak'},
        {'text': 'If you think lifting is dangerous, try being weak. Being weak is dangerous.', 'auther': 'Bret Contreras'},
        {'text': 'The only place where success comes before work is in the dictionary.', 'auther': 'Vidal Sassoon'},
        {'text': 'The clock is ticking. Are you becoming the person you want to be?', 'auther': 'Greg Plitt'},
        {'text': 'Whether you think you can, or you think you can’t, you’re right.', 'auther': 'Henry Ford'},
        {'text': 'The successful warrior is the average man, with laser-like focus.', 'auther': 'Bruce Lee'},
        {'text': 'You must expect great things of yourself before you can do them.', 'auther': 'Michael Jordan'},
        {'text': 'Action is the foundational key to all success.', 'auther': 'Pablo Picasso'},
        {'text': 'Everyone is a bot', 'auther': 'Asaf sh'}
        ]
    

    def __init__(self, *args, **kwargs):
        super(MotivationQuotesCommand, self).__init__(*args, **kwargs)

    @get_trainee_and_group
    def _handler(self, bot, update, trainee, group):
        """Override method to handle motivation quote command.

        Randomize a number between 0 and the number of quotes -1 and send quote in this index back to the chat.

        """
        self.logger.info('%s asked to be motivated in %s', trainee, group)

        random_number = random.randint(0, len(self.QUOTE_LIST)-1 )

        random_quote = self.QUOTE_LIST[random_number]

        update.message.reply_text(quote=True,
                                  text=self.compose_quote(random_quote))
    
    def compose_quote(self, quote_object):
        return self.QUOTE_MSG.format(
                                text=quote_object.text,
                                auther=quote_object.auther
                                )


