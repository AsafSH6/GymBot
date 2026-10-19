from telegram import Update
from telegram.ext import CallbackContext

from gym_bot_app.decorators import get_trainee_and_group
from gym_bot_app.commands import Command
import textwrap

from gym_bot_app.models import Trainee, Group


class MyStatisticsCommand(Command):
    """Telegram gym bot my statistics command.

    Sends training statistics of the requested trainee.

    """
    DEFAULT_COMMAND_NAME = 'my_statistics'
    TRAINEE_STATISTICS_MSG = textwrap.dedent('''
        מספר הימים שהתאמנת בהם: {trained_days}
        מספר הימים שהיית אפס הוא: {missed_training_days}
        אחוז שור עולמיות: {percentage}%
        מספר ממוצע של ימי אימון בשבוע: {num_of_training_days_per_week}
        {level}
        ''')
    SEASON_MSG = 'עונה {number} (מאז {started_at})'
    PAST_SEASONS_MSG = 'עונות קודמות:'
    PAST_SEASON_MSG = 'עונה {number}: {level}, {trained_days} ימי אימון'
    SEASON_DATE_FORMAT = '%d/%m/%Y'

    def __init__(self, *args, **kwargs):
        super(MyStatisticsCommand, self).__init__(*args, **kwargs)

    @get_trainee_and_group
    def _handler(self, update: Update, context: CallbackContext, trainee: Trainee, group: Group):
        """Override method to handle my statistics command.

        Checks the trained days of the requested trainee and sends it back to the chat.

        """
        self.logger.info('My statistics command with %s in %s', trainee, group)

        (trained_days, missed_training_days,
         training_percentage, num_of_training_days_per_week) = trainee.get_training_statistics()

        msg = self.TRAINEE_STATISTICS_MSG.format(
            trained_days=trained_days,
            missed_training_days=missed_training_days,
            percentage=training_percentage,
            num_of_training_days_per_week='{:.2f}'.format(num_of_training_days_per_week),
            level=trainee.level
        )

        if trainee.past_seasons:
            season_msg = self.SEASON_MSG.format(number=trainee.season_number,
                                                started_at=trainee.season_started_at.strftime(self.SEASON_DATE_FORMAT))
            past_seasons_msg = '\n'.join(
                self.PAST_SEASON_MSG.format(number=season.number,
                                            level=season.level,
                                            trained_days=trainee.count_trained_days_in_past_season(season))
                for season in trainee.past_seasons
            )
            msg = '{season}{statistics}\n{past_seasons_title}\n{past_seasons}'.format(
                season=season_msg,
                statistics=msg,
                past_seasons_title=self.PAST_SEASONS_MSG,
                past_seasons=past_seasons_msg
            )

        update.message.reply_text(quote=True, text=msg)

