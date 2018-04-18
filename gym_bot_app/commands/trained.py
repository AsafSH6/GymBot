# encoding: utf-8
from __future__ import unicode_literals

from datetime import datetime

from gym_bot_app.commands import Command
from gym_bot_app import FACEPALMING_EMOJI
from gym_bot_app.decorators import get_trainee
from gym_bot_app.utils import trainee_already_marked_training_date


class TrainedCommand(Command):
    """Telegram gym bot trained command.

    Allows trainees to report that they trained today.

    """
    DEFAULT_COMMAND_NAME = 'trained'
    TRAINED_TODAY_MSG = 'שור עולם'
    ALREADY_REPORTED_TRAINING_STATUS_MSG = 'כבר אמרת שהתאמנת היום יא בוט {}'.format(FACEPALMING_EMOJI)

    def __init__(self, *args, **kwargs):
        super(TrainedCommand, self).__init__(*args, **kwargs)

    @get_trainee
    def _handler(self, bot, update, trainee):
        """Override method to handle trained command.

        Creates training day info of today.

        """
        self.logger.info('Trained command with %s', trainee)

        today_date = datetime.now().date()
        if trainee_already_marked_training_date(trainee=trainee, training_date=today_date):
            self.logger.debug('Trainee already reported today about training status')
            bot.send_message(chat_id=update.message.chat_id,
                             reply_to_message_id=update.message.message_id,
                             text=self.ALREADY_REPORTED_TRAINING_STATUS_MSG)
        else:
            bot.send_message(chat_id=update.message.chat_id,
                             reply_to_message_id=update.message.message_id,
                             text=self.TRAINED_TODAY_MSG)
            trainee.add_training_info(training_date=today_date, trained=False)

