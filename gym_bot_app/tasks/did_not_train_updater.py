from datetime import time, timedelta, datetime
from typing import List

from telegram import ParseMode

from gym_bot_app.models import Trainee, Group
from gym_bot_app.tasks import Task
from gym_bot_app.utils import get_trainees_that_selected_today_and_did_not_train_yet
from gym_bot_app.decorators import repeats, run_for_all_groups


class DidNotTrainUpdaterTask(Task):
    """Telegram gym bot update trainee did not go to gym task."""
    DEFAULT_TARGET_TIME = time(hour=23, minute=55, second=0, microsecond=0)
    DID_NOT_TRAIN_QUERY_IDENTIFIER = 'did_not_train_updater'

    DATE_FORMAT = '%d/%m/%Y'
    
    DID_NOT_GO_TO_GYM_PLURAL_MSG = 'אפסים מאופסים {trainees}'
    WENT_TO_GYM_INDIVIDUAL_MSG = 'אפס מאופס {trainees}'

    def __init__(self, target_time=None, *args, **kwargs):
        super(DidNotTrainUpdaterTask, self).__init__(*args, **kwargs)
        self.target_time = target_time or self.DEFAULT_TARGET_TIME

    def get_start_time(self):
        """Start time of did not train updater based on the target time."""
        return self._seconds_until_time(target_time=self.target_time)

    @repeats(every_seconds=timedelta(days=1).total_seconds())
    @run_for_all_groups
    def execute(self, group: Group):
        """Override method to execute did not train updater.

        Sends did not go to gym message with the trainees of today that did not train to the given group chat.
        """
        self.logger.info('Executing did not train updater with %s', group)

        relevant_trainees = get_trainees_that_selected_today_and_did_not_train_yet(group)
        self.logger.debug('Relevant trainees %s', relevant_trainees)

        if relevant_trainees:
            # The use of timedelta here is to make sure that we remain within the same day we wanted to
            not_trained_time = (datetime.today() - timedelta(hours=2)).date()
            for trainee in relevant_trainees:
                if not trainee.get_training_info(training_date=not_trained_time):
                    trainee.add_training_info(training_date=not_trained_time, trained=False)
            did_not_go_to_gym_msg = self._get_did_not_go_to_gym_msg(relevant_trainees)
            self.updater.bot.send_message(chat_id=group.id, text=did_not_go_to_gym_msg, parse_mode=ParseMode.MARKDOWN)
                
        else:
            self.logger.debug('There are no trainees that said they would train and did not')

    def _get_did_not_go_to_gym_msg(self, trainees: List[Trainee]):
        """Generate did not go to gym message based on the given trainees.

        Args:
            trainees(list): trainees that will be included in the message.

        Returns:
            str. message of did not go to gym with the given trainees.

        """
        trainee_string = ' '.join(trainee.get_mention_string() for trainee in trainees)

        if len(trainees) > 1:
            self.logger.debug('More than one trainee therefore creating plural msg')
            did_not_go_msg = self.DID_NOT_GO_TO_GYM_PLURAL_MSG.format(trainees=trainee_string)
        else:
            self.logger.debug('One trainee creating msg for individual')
            did_not_go_msg = self.WENT_TO_GYM_INDIVIDUAL_MSG.format(trainees=trainee_string)

        return did_not_go_msg
