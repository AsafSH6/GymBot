# encoding: utf-8
from __future__ import unicode_literals

from gym_bot_app.decorators import get_trainee_and_group
from gym_bot_app.commands import (Command,
                                  SelectDaysCommand)


class MyDaysCommand(Command):
    """Telegram gym bot my days command.

    Sends the selected training days of the requested trainee.

    """
    DEFAULT_COMMAND_NAME = 'my_days'
    NO_DAYS_SELECTED_MESSAGE = 'לא בחרת ימים להתאמן יא בוט. קח תתפנק'

    def __init__(self, *args, **kwargs):
        super(MyDaysCommand, self).__init__(*args, **kwargs)

    @get_trainee_and_group
    def _handler(self, bot, update, trainee, group):
        """Override method to handle my days command.

        Checks the training days of the requested trainee and sends it back to the chat.
        If trainee did not select any training days, sends select days keyboard based on SelectDaysCommand keyboard.

        """
        self.logger.info('My days command with %s in %s', trainee, group)

        training_days = ', '.join(day.name for day in trainee.training_days.filter(selected=True))
        if training_days:  # trainee has selected training days.
            self.logger.debug('Trainee days %s', training_days)
            update.message.reply_text(quote=True, text=training_days)
        else:  # trainee did not select any training days.
            self.logger.debug('Trainee does not have any training days')
            select_days_keyboard = SelectDaysCommand.get_select_days_keyboard(trainee=trainee)
            update.message.reply_text(quote=True,
                                      text=self.NO_DAYS_SELECTED_MESSAGE,
                                      reply_markup=select_days_keyboard)
