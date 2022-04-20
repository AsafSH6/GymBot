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
    DID_NOT_PROVIDE_LEGAL_MONTH = 'לא הכנסת חדוש תקין יא בוט'

    @get_group
    def _handler(self, update: Update, context: CallbackContext, group: Group):
        """Override method to handle month ranking command.

        Takes top trainees based on their average monthly training.

        """
        self.logger.info('Month ranking statistics command in %s', group)

        month = 0
        if len(context.args) == 0:
            month = datetime.now().month
            self.logger.debug('Trainee did not provide month - using current month (%d)', month)

        elif not any(chr.isdigit() for chr in context.args[0]):
            self.logger.debug('Trainee did not provide legal month (month=%s)', context.args[0])
            update.message.reply_text(quote=True, text=self.DID_NOT_PROVIDE_LEGAL_MONTH)
            return
        else:
            month = int(context.args[0])

        if month <= 0 or month > 12:
            self.logger.debug('Trainee did not provide legal month (month=%s)', context.args[0])
            update.message.reply_text(
                quote=True, text=self.DID_NOT_PROVIDE_LEGAL_MONTH)
            return

        trainees_properties = [
            self._get_trainee_properties(trainee=trainee, month=month) 
            for trainee in group.trainees
        ]
        ranking = sorted(trainees_properties,
                         key=lambda trainee: trainee['average'],
                         reverse=True)[:self.TRAINEES_LIMIT]
        self.logger.debug('Group month average statistics training is %s', ranking)

        msg = 'Ranking for {month} {year}:\n'.format( month=month_name[month], year=datetime.now().year)
        msg += '\n'.join(
            '{idx}. {name} <Average {average} ({trained_days_count}/{days_in_month})>'.format(
                idx=(idx + 1),
                name=trainee['name'],
                trained_days_count=trainee['trained_days_count'],
                days_in_month=trainee['days_in_month'],
                average='{:.2f}'.format(trainee['average']),
            )
            for idx, trainee in enumerate(ranking)
        )
        update.message.reply_text(quote=True,
                                  text=msg)

    def _get_trainee_properties(self, trainee, month):
        (trained_days_count, days_in_month,
            average) = trainee.calculate_average_training_days_for_this_month(month)
        return {
            'name': trainee.first_name,
            'trained_days_count': trained_days_count,
            'days_in_month': days_in_month,
            'average': average,
        }