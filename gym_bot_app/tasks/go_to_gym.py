# encoding: utf-8
from __future__ import unicode_literals

from datetime import time, timedelta

from telegram.vendor.ptb_urllib3.urllib3.util.timeout import Timeout

from gym_bot_app.tasks.task import Task
from gym_bot_app.decorators import repeats, run_for_all_groups


class GoToGymTask(Task):
    TARGET_TIME = time(hour=23, minute=23, second=0, microsecond=0)

    GO_TO_GYM_PLURAL = 'לכו היום לחדר כושר יא בוטים {training}'
    GO_TO_GYM_INDIVIDUAL = 'לך היום לחדר כושר יא בוט {training}'

    def __init__(self, *args, **kwargs):
        super(GoToGymTask, self).__init__(*args, **kwargs)

    @repeats(every_seconds=timedelta(minutes=1).total_seconds())
    @run_for_all_groups
    def execute(self, group):
        self.logger.info('checking group %s', group)
        relevant_trainees = group.get_trainees_of_today()
        self.logger.info('relevant trainees %s', relevant_trainees)

        if not relevant_trainees:
            self.logger.info('there are no relevant trainees')
            return

        training_today_msg = ' '.join(trainee.first_name for trainee in relevant_trainees)

        if len(relevant_trainees) > 1:
            self.logger.info('more than one trainee therefore creating plural msg')
            text = self.GO_TO_GYM_PLURAL.format(training=training_today_msg)
        else:
            self.logger.info('one trainee creating msg for individual')
            text = self.GO_TO_GYM_INDIVIDUAL.format(training=training_today_msg)

        try:
            self.updater.bot.send_message(chat_id=group.id, text=text)
            self.logger.info('finished to remind to group %s', group)
        except Timeout:
            self.logger.error('Timeout occurred')

    def get_start_time(self):
        return self._seconds_until_time(target_time=self.TARGET_TIME)
