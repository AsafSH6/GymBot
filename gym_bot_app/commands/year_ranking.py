from telegram import Update
from telegram.ext import CallbackContext
from datetime import datetime


from gym_bot_app.decorators import get_group
from gym_bot_app.commands import Command
from gym_bot_app.models import Group


class YearRankingCommand(Command):
    """Telegram gym bot year ranking command.

    Sends group year ranking based on trainees statistics.

    """
    DEFAULT_COMMAND_NAME = 'year_ranking'
    TRAINEES_LIMIT = 10
    DID_NOT_PROVIDE_LEGAL_YEAR = 'לא הכנסת שנה תקינה יא בוט'
    RANKING_ENTRY_TEMPLATE = '{idx}. {name} <{training_percentage}% ({trained_days_count}/{days_in_year})>'

    @get_group
    def _handler(self, update: Update, context: CallbackContext, group: Group):
        """Override method to handle year ranking command.

        Takes top trainees based on their statistics yearly training.

        """
        self.logger.info('Year ranking statistics command in %s', group)

        today = datetime.now()
        if len(context.args) == 0:
            year = today.year
            self.logger.debug('Trainee did not provide year - using current year (%d)', year)
        else:
            selected_year = context.args[0]
            if not (selected_year.isdigit()):
                self.logger.debug('Trainee did not provide legal year (year=%s)', selected_year)
                update.message.reply_text(quote=True, text=self.DID_NOT_PROVIDE_LEGAL_YEAR)
                return

            year = int(selected_year)
            if year <= 0 or year > today.year:
                self.logger.debug('Trainee did not provide legal year (year=%s)', selected_year)
                update.message.reply_text(
                    quote=True, text=self.DID_NOT_PROVIDE_LEGAL_YEAR)
                return

        trainees_properties = [
            self._get_trainee_properties(trainee=trainee, year=year)
            for trainee in group.trainees
        ]
        ranking = sorted(trainees_properties,
                         key=lambda trainee: trainee['training_percentage'],
                         reverse=True)[:self.TRAINEES_LIMIT]
        self.logger.debug('Group year %s statistics training is %s', year, ranking)

        msg = 'Ranking for {year}:\n'.format(year=year)
        if year == today.year:
            # Add explanation for current year
            msg += '(Showing statistics up to today, not the full year)\n'
        msg += '\n'.join(
            self.RANKING_ENTRY_TEMPLATE.format(
                idx=(idx + 1),
                name=trainee_rank['name'],
                trained_days_count=trainee_rank['trained_days_count'],
                days_in_year=trainee_rank['days_in_year'],
                training_percentage=trainee_rank['training_percentage'],
            )
            for idx, trainee_rank in enumerate(ranking)
        )
        update.message.reply_text(quote=True,
                                  text=msg)

    @staticmethod
    def _get_trainee_properties(trainee, year):
        (trained_days_count,
         days_in_year,
         training_percentage) = trainee.calculate_statistics_training_days_for_this_year(year)

        return {
            'name': trainee.first_name,
            'trained_days_count': trained_days_count,
            'days_in_year': days_in_year,
            'training_percentage': training_percentage,
        }

