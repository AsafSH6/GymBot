from datetime import time, timedelta
from typing import List

from gym_bot_app.models import Group, Trainee
from gym_bot_app.tasks import Task
from gym_bot_app.decorators import repeats, run_for_all_groups
from gym_bot_app.utils import get_trainees_that_selected_today_and_did_not_train_yet


class GoToGymTask(Task):
    """Telegram gym bot go to gym task."""
    DEFAULT_TARGET_TIME = time(hour=9, minute=0, second=0, microsecond=0)

    GO_TO_GYM_PLURAL = 'לכו היום לחדר כושר יא בוטים {trainees}'
    GO_TO_GYM_INDIVIDUAL = 'לך היום לחדר כושר יא בוט {trainees}'

    def __init__(self, target_time=None, *args, **kwargs):
        super(GoToGymTask, self).__init__(*args, **kwargs)
        self.target_time = target_time or self.DEFAULT_TARGET_TIME

    def get_start_time(self):
        """Start time of go to gym task based on the target time."""
        return self._seconds_until_time(target_time=self.target_time)

    @repeats(every_seconds=timedelta(days=1).total_seconds())
    @run_for_all_groups
    def execute(self, group: Group):
        """Override method to execute go to gym task.

        Sends go to gym message with the trainees of today to the given group chat.

        """
        self.logger.info('Executing go to gym task with %s', group)

        relevant_trainees = get_trainees_that_selected_today_and_did_not_train_yet(group)
        self.logger.debug('Relevant trainees %s', relevant_trainees)

        if not relevant_trainees:
            self.logger.debug('There are no relevant trainees')
            return

        go_to_gym_msg = self._get_go_to_gym_msg(trainees=relevant_trainees)
        self.updater.bot.send_message(chat_id=group.id, text=go_to_gym_msg)

    def _get_go_to_gym_msg(self, trainees: List[Trainee]) -> str:
        """Generate go to gym message based on the given trainees.

        Args:
            trainees(list): trainees that will be included in the message.

        Returns:
            str. message of go to gym with the given trainees.

        """
        training_today_msg = ' '.join(trainee.first_name for trainee in trainees)

        if len(trainees) > 1:
            self.logger.debug('More than one trainee therefore creating plural msg')
            go_to_gym_msg = self.GO_TO_GYM_PLURAL.format(trainees=training_today_msg)
        else:
            self.logger.debug('One trainee creating msg for individual')
            go_to_gym_msg = self.GO_TO_GYM_INDIVIDUAL.format(trainees=training_today_msg)

        return go_to_gym_msg
