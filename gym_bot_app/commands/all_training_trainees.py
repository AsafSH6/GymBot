from telegram import Update
from telegram.ext import CallbackContext

from gym_bot_app.models import Day, Group
from gym_bot_app.commands import Command
from gym_bot_app.decorators import get_group


class AllTrainingTraineesCommand(Command):
    """Telegram gym bot all training trainees command.

    Sends the selected training days of all trainees in the requested group.

    """
    DEFAULT_COMMAND_NAME = 'all_training_trainees'
    NOBODY_TRAINING_MARK = '-'

    def __init__(self, *args, **kwargs):
        super(AllTrainingTraineesCommand, self).__init__(*args, **kwargs)

    @get_group
    def _handler(self, update: Update, context: CallbackContext, group: Group):
        """Override method to handle all training trainees command.

        Checks the training days of all trainees in the given group and send it back to the chat.

        """
        self.logger.info('All training trainees command with %s', group)

        days_and_trainees = []
        for day in Day.get_week_days():
            trainees_in_day = group.get_trainees_in_day(day.name)
            self.logger.debug('Trainees in day %s are %s', day.name, trainees_in_day)

            training_trainees = self._get_msg_of_training_trainees_in_day(trainees_in_day=trainees_in_day,
                                                                          day_name=day.name)
            days_and_trainees.append(training_trainees)

        update.message.reply_text(text='\n'.join(days_and_trainees))

    def _get_msg_of_training_trainees_in_day(self, trainees_in_day, day_name):
        """Get message of the training trainees in the given day.

        Args:
            trainees_in_day(list): trainees to include in the message.
            day_name(str): name of the day.

        Returns:
              str. training trainees message in the given day based on trainees_in_day and day_name.

        """
        if trainees_in_day:
            trainees_names = ', '.join(trainee.first_name for trainee in trainees_in_day)
        else:
            trainees_names = self.NOBODY_TRAINING_MARK

        return '{day_name}: {trainees}'.format(day_name=day_name,
                                               trainees=trainees_names)
