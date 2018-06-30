# encoding: utf-8
from __future__ import unicode_literals

from gym_bot_app.decorators import get_trainee_and_group
from gym_bot_app.commands import Command
from gym_bot_app.models import TrainingDayInfo
import textwrap


class MyStatistics(Command):
    """Telegram gym bot my statistics command.

    Sends training statistics of the requested trainee.

    """
    DEFAULT_COMMAND_NAME = 'my_statistics'
    TRAINEE_STATISTICS_MSG = textwrap.dedent('''
    Total number of days you trained: {trained_days}
    Total number of days you were a loser: {missed_training_days}
    Percentage: {percentage}%
    ''')

    def __init__(self, *args, **kwargs):
        super(MyStatistics, self).__init__(*args, **kwargs)

    @get_trainee_and_group
    def _handler(self, bot, update, trainee, group):
        """Override method to handle my statistics command.

        Checks the trained days of the requested trainee and sends it back to the chat.

        """
        self.logger.info('My days command with %s in %s', trainee, group)

        training_days_info = TrainingDayInfo.objects.filter(trainee=trainee)
        trained_days = training_days_info.filter(trained=True).count()
        missed_training_days = training_days_info.filter(trained=False).count()
        update.message.reply_text(quote=True,
                                  text=self.TRAINEE_STATISTICS_MSG.format(
                                      trained_days=trained_days,
                                      missed_training_days=missed_training_days,
                                      percentage=(100 /(missed_training_days + trained_days) * trained_days)))

