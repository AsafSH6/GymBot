# encoding: utf-8
from __future__ import unicode_literals

from datetime import time, timedelta

from gym_bot_app.models import Group
from gym_bot_app.tasks.task import Task
from gym_bot_app.decorators import repeats


class GoToGymTask(Task):
    TARGET_TIME = time(hour=9, minute=0, second=0, microsecond=0)

    def __init__(self, *args, **kwargs):
        super(GoToGymTask, self).__init__(*args, **kwargs)

    def get_start_time(self):
        return self._seconds_until_time(target_time=self.TARGET_TIME)

    @repeats(every_seconds=timedelta(minutes=1).total_seconds())
    def execute(self):
        self.logger.info('reminding to go to the gym')
        for group in Group.objects:
            self.logger.info('checking group %s', group)
            relevant_trainees = group.get_trainees_of_today()
            self.logger.info('relevant trainees %s', relevant_trainees)

            if not relevant_trainees:
                self.logger.info('there are no relevant trainees')
                return

            go_to_gym_plural = 'לכו היום לחדר כושר יא בוטים {training}'
            go_to_gym_individual = 'לך היום לחדר כושר יא בוט {training}'

            training_today_msg = ' '.join(trainee.first_name for trainee in relevant_trainees)

            if len(relevant_trainees) > 1:
                self.logger.info('more than one trainee therefore creating plural msg')
                text = go_to_gym_plural.format(training=training_today_msg)
            else:
                self.logger.info('one trainee creating msg for individual')
                text = go_to_gym_individual.format(training=training_today_msg)

            self.updater.bot.send_message(chat_id=group.id, text=text)
            self.logger.info('finished to remind to group %s', group)
