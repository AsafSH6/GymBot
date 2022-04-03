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

    @get_group
    def _handler(self, update: Update, context: CallbackContext, group: Group):
        """Override method to handle month ranking command.

        Takes top trainees based on their average monthly training.

        """
        DID_NOT_PROVIDE_LEGAL_MONTH = 'לא הכנסת חדוש תקין יא בוט'

        self.logger.info('Ranking statistics command in %s', group)

        def _get_trainee_properties(trainee):
            (trained_days_count, days_in_month,
             average) = trainee.calculate_average_training_days_for_this_month(month)
            return {
                'name': trainee.first_name,
                'trained_days_count': trained_days_count,
                'days_in_month': days_in_month,
                'average': average,
            }

        month = context.args
        if len(month) == 0:
            self.logger.debug('Trainee did not provide month')
            month = datetime.now().month

        elif not any(chr.isdigit() for chr in month):
            self.logger.debug('Trainee did not provide legal month')
            update.message.reply_text(quote=True, text=self.DID_NOT_PROVIDE_LEGAL_MONTH)
            return

        month = int(month)

        if month <= 0 or month > 12:
            self.logger.debug('Trainee did not provide legal month')
            update.message.reply_text(
                quote=True, text=self.DID_NOT_PROVIDE_LEGAL_MONTH)
            return

        trainees = list(map(_get_trainee_properties, group.trainees))
        ranking = sorted(trainees,
                         key=lambda trainee: trainee['average'],
                         reverse=True)[:self.TRAINEES_LIMIT]
        self.logger.debug('Group month average statistics training is %s', ranking)

        msg = '\n'.join(
            'Ranking for {month} {year}:\n {idx}. {name} <Average {average} ({trained_days_count}/{days_in_month})>'.format(
                idx=(idx + 1),
                name=trainee['name'],
                month=month_name[month],
                year=datetime.now().year,
                trained_days_count=trainee['trained_days_count'],
                days_in_month=trainee['days_in_month'],
                average='{:.2f}'.format(trainee['average']),
            )
            for idx, trainee in enumerate(ranking)
        )
        update.message.reply_text(quote=True,
                                  text=msg)

        
