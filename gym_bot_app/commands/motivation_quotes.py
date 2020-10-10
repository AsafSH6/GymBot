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
    
    class Quote():
        
        def __init__(self, text, auther):
            self.text = text
            self.auther = auther
            self.quote_msg = textwrap.dedent('"{text}", {auther}')

        @property
        def text(self, text):
            return text
        
        @property
        def auther(self,auther):
            return auther
        
        def compose_quote(self):
            return self.quote_msg.format(
                                    text=self.text,
                                    auther=self.auther
                                    )

    DEFAULT_COMMAND_NAME = 'motivate_me'
    
    QUOTE_LIST = [
        Quote('The last three or four reps is what makes the muscle grow. This area of pain divides a champion from someone who is not a champion.', 'Arnold Schwarzenegger'),
        Quote('Success usually comes to those who are too busy to be looking for it.','Henry David Thoreau'),
        Quote('All progress takes place outside the comfort zone','Michael John Bobak'),
        Quote('If you think lifting is dangerous, try being weak. Being weak is dangerous.','Bret Contreras'),
        Quote('The only place where success comes before work is in the dictionary.','Vidal Sassoon'),
        Quote('The clock is ticking. Are you becoming the person you want to be?','Greg Plitt'),
        Quote('Whether you think you can, or you think you can’t, you’re right.','Henry Ford,'),
        Quote('The successful warrior is the average man, with laser-like focus.','Bruce Lee'),
        Quote('You must expect great things of yourself before you can do them.','Michael Jordan'),
        Quote('Action is the foundational key to all success.','Pablo Picasso')
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
                                  text=random_quote.compose_quote())

