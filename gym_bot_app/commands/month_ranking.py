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
    DID_NOT_PROVIDE_LEGAL_MONTH = 'לא הכנסת חודש תקין יא בוט'

    @get_group
    def _handler(self, update: Update, context: CallbackContext, group: Group):
        """Override method to handle month ranking command.

        Takes top trainees based on their statistics monthly training.

        """
        self.logger.info('Month ranking statistics command in %s', group)

        date = datetime.now()
        if len(context.args) == 0:
            month = date.month
            self.logger.debug('Trainee did not provide month - using current month (%d)', month)
        else:
            selected_month = context.args[0]
            if not any(s.isdigit() for s in selected_month):
                self.logger.debug('Trainee did not provide legal month (month=%s)', selected_month)
                update.message.reply_text(quote=True, text=self.DID_NOT_PROVIDE_LEGAL_MONTH)
                return

            month = int(selected_month)
            if month <= 0 or month > 12:
                self.logger.debug('Trainee did not provide legal month (month=%s)', selected_month)
                update.message.reply_text(
                    quote=True, text=self.DID_NOT_PROVIDE_LEGAL_MONTH)
                return

        trainees_properties = [
            self._get_trainee_properties(trainee=trainee, month=month)
            for trainee in group.trainees
        ]
        ranking = sorted(trainees_properties,
                         key=lambda trainee: trainee['training_percentage'],
                         reverse=True)[:self.TRAINEES_LIMIT]
        self.logger.debug('Group month %s statistics training is %s', month, ranking)

        msg = 'Ranking for {month} {year}:\n'.format(month=month_name[month], year=date.year)
        msg += '\n'.join(
            '{idx}. {name} <{training_percentage}% ({trained_days_count}/{days_in_month})>'.format(
                idx=(idx + 1),
                name=trainee_rank['name'],
                trained_days_count=trainee_rank['trained_days_count'],
                days_in_month=trainee_rank['days_in_month'],
                training_percentage=trainee_rank['training_percentage'],
            )
            for idx, trainee_rank in enumerate(ranking)
        )
        update.message.reply_text(quote=True,
                                  text=msg)

    @staticmethod
    def _get_trainee_properties(trainee, month):
        (trained_days_count,
         days_in_month,
         training_percentage) = trainee.calculate_statistics_training_days_for_this_month(month)

        return {
            'name': trainee.first_name,
            'trained_days_count': trained_days_count,
            'days_in_month': days_in_month,
            'training_percentage': training_percentage,
        }
