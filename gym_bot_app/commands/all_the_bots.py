# encoding: utf-8
from __future__ import unicode_literals

from gym_bot_app.commands.command import Command
from gym_bot_app.decorators import get_group
from gym_bot_app.models import Day


class AllTheBotsCommand(Command):
    NAME = 'all_the_bots'
    NOBODY_TRAINING_MARK = '-'

    def __init__(self, *args, **kwargs):
        super(AllTheBotsCommand, self).__init__(*args, **kwargs)

    @get_group
    def _handler(self, bot, update, group):
        days_and_trainees = []
        for day in Day.get_week_days():
            trainees_in_day = group.get_trainees_in_day(day.name)
            training_trainees = self._get_training_trainees_in_day_msg(trainees_in_day=trainees_in_day,
                                                                       day_name=day.name)
            days_and_trainees.append(training_trainees)

        bot.send_message(chat_id=update.message.chat_id,
                         text='\n'.join(days_and_trainees))

    def _get_training_trainees_in_day_msg(self, trainees_in_day, day_name):
        if trainees_in_day:
            trainees_names = ', '.join(trainee.first_name for trainee in trainees_in_day)
        else:
            trainees_names = self.NOBODY_TRAINING_MARK

        return '{day_name}: {trainees}'.format(day_name=day_name,
                                               trainees=trainees_names)
