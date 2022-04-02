from telegram import Update
from telegram.ext import CallbackContext
from datetime import datetime
from calendar import month_name


from gym_bot_app.decorators import get_group
from gym_bot_app.commands import Command
from gym_bot_app.models import Group


class MonthRankingCommand(Command):
    """Telegram gym bot month ranking command.

    Sends group month ranking based on trainees statistics.

    """
    DEFAULT_COMMAND_NAME = 'month_ranking'
    TRAINEES_LIMIT = 10

    def __init__(self, *args, **kwargs):
        super(MonthRankingCommand, self).__init__(*args, **kwargs)

    @get_group
    def _handler(self, update: Update, context: CallbackContext, group: Group):
        """Override method to handle month ranking command.

        Takes top trainees based on their average monthly training.

        """
        DID_NOT_PROVIDE_LEGAL_MONTH = 'לא הכנסת חדוש תקין יא בוט'

        self.logger.info('Ranking statistics command in %s', group)

        month =  ' '.join(context.args)
        if len(month) == 0:
            self.logger.debug('Trainee did not provide month')
            month = datetime.now().month

        elif not any(chr.isdigit() for chr in month) or int(month) <= 0 or int(month) > 12:
            self.logger.debug('Trainee did not provide legal month')
            update.message.reply_text(quote=True, text=self.DID_NOT_PROVIDE_LEGAL_MONTH)
            return

        month = int(month)
        ranking = sorted(group.trainees,
                         key=lambda trainee: trainee.calculate_average_training_days_for_this_month(month)[2],
                         reverse=True)[:self.TRAINEES_LIMIT]
        self.logger.debug('Group month average statistics training is %s', ranking)

        msg = '\n'.join(
            'Ranking for {month} {year}:\n {idx}. {name} <Average {obj[2]} ({obj[0]}/{obj[1]})>'.format(
                idx=(idx + 1),
                name=trainee.first_name,
                month=month_name[month],
                year=datetime.now().year,
                obj=trainee.calculate_average_training_days_for_this_month(month)
            )
            for idx, trainee in enumerate(ranking)
        )
        update.message.reply_text(quote=True,
                                  text=msg)
