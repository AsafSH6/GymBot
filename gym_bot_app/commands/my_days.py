# encoding: utf-8
from __future__ import unicode_literals

from gym_bot_app.commands.command import Command
from gym_bot_app.commands.select_days import SelectDaysCommand
from gym_bot_app.decorators import get_trainee


class MyDaysCommand(Command):
    NAME = 'my_days'
    NO_DAYS_SELECTED_MESSAGE = 'לא בחרת ימים להתאמן יא בוט. קח תתפנק'

    def __init__(self, *args, **kwargs):
        super(MyDaysCommand, self).__init__(*args, **kwargs)

    @get_trainee
    def _handler(self, bot, update, trainee):
        self.logger.info('my days command')
        self.logger.info('requested by trainee %s', trainee)

        training_days = ', '.join(day.name for day in trainee.training_days.filter(selected=True))
        if training_days:
            self.logger.info('trainee days %s', training_days)
            bot.send_message(chat_id=update.message.chat_id,
                             reply_to_message_id=update.message.message_id,
                             text=training_days)
        else:
            self.logger.info('trainee does not have any training days')
            select_days_keyboard = SelectDaysCommand.get_select_days_keyboard_for_trainee(trainee)
            bot.send_message(chat_id=update.message.chat_id,
                             reply_to_message_id=update.message.message_id,
                             text=self.NO_DAYS_SELECTED_MESSAGE,
                             reply_markup=select_days_keyboard)

