# encoding: utf-8
from __future__ import unicode_literals

from datetime import datetime

from gym_bot_app.commands import Command
from gym_bot_app import FACEPALMING_EMOJI
from gym_bot_app.decorators import get_trainee_and_group
from gym_bot_app.utils import trainee_already_marked_training_date


class TrainedCommand(Command):
    """Telegram gym bot trained command.

    Allows trainees to report that they trained today.

    """
    DEFAULT_COMMAND_NAME = 'trained'
    TRAINED_TODAY_MSG = 'שור עולם'
    TRAINED_TODAY_MSG_TO_OTHER_GROUPS = 'השור עולם התאמן היום {trainee}'
    ALREADY_REPORTED_TRAINING_STATUS_MSG = 'כבר אמרת שהתאמנת היום יא בוט {}'.format(FACEPALMING_EMOJI)

    def __init__(self, *args, **kwargs):
        super(TrainedCommand, self).__init__(*args, **kwargs)

    @get_trainee_and_group
    def _handler(self, bot, update, trainee, group):
        """Override method to handle trained command.

        Creates training day info of today.

        """
        self.logger.info('Trained command with %s in %s', trainee, group)

        today_date = datetime.now().date()
        if trainee_already_marked_training_date(trainee=trainee, training_date=today_date):
            self.logger.debug('Trainee already reported today about training status')
            update.message.reply_text(quote=True, text=self.ALREADY_REPORTED_TRAINING_STATUS_MSG)
        else:
            update.message.reply_text(quote=True, text=self.TRAINED_TODAY_MSG)
            trainee.add_training_info(training_date=today_date, trained=True)

            other_groups = (g for g in trainee.groups if g != group)
            for other_group in other_groups:
                bot.send_message(chat_id=other_group.id,
                                 text=self.TRAINED_TODAY_MSG_TO_OTHER_GROUPS.format(trainee=trainee.first_name))
