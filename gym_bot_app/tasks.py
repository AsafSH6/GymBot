# encoding: utf-8
from __future__ import unicode_literals

import os
import logging
import threading
from telegram.ext import Updater
from gym_bot_app.models import Trainee, Group
from datetime import datetime, time, timedelta


logging.basicConfig(filename='logs/gymbot.log',
                    encoding='utf-8',
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)


def repeats(every_seconds):
    def decorator(func):
        def wrapper(*args, **kwargs):
            threading.Timer(every_seconds,
                            wrapper,
                            args=args,
                            kwargs=kwargs).start()
            logger.info('scheduled function %s with args %s and kwargs %s in %s seconds',
                        func.func_name,
                        args,
                        kwargs,
                        every_seconds)
            return func(*args, **kwargs)
        return wrapper
    return decorator


class Task(object):
    def __init__(self, updater, logger):
        self.updater = updater
        self.logger = logger

    def _seconds_until_time(self, target_time):
        now = datetime.today()
        self.logger.info('requested target time is %s', target_time)
        desired_datetime = now.replace(hour=target_time.hour,
                                       minute=target_time.minute,
                                       second=target_time.second)
        if now > desired_datetime:  # time already passed- move to the next day.
            self.logger.info('the time already passed, targeting time for for tomorrow')
            desired_datetime += timedelta(days=1)
        else:
            self.logger.info('the time did not pass, targeting time for today')
        self.logger.info('requested target datetime is %s', desired_datetime)

        return (desired_datetime - now).total_seconds()

    def get_start_time(self):
        raise NotImplementedError('Not implemented start time method.')

    def execute(self, *args, **kwargs):
        raise NotImplementedError('Not implemented execute method.')

    def run(self, *args, **kwargs):
        self.logger.info('running task %s', self.__class__.__name__)
        start_time = self.get_start_time()
        self.logger.info('request task time is in %s seconds', start_time)
        if start_time < 0:
            self.logger.error('start time already passed')
            raise RuntimeError('%s start time already passed' % self.__class__.__name__)

        threading.Timer(start_time,
                        self.execute,
                        args=args,
                        kwargs=kwargs).start()
        self.logger.info('started task')


class GoToGymTask(Task):
    TARGET_TIME = time(hour=23, minute=54, second=0, microsecond=0)

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

            # self.updater.bot.send_message(chat_id=group.id, text=text)
            self.logger.info('finished to remind to group %s', group)


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        os.environ['BOT_TOKEN'] = os.environ['BOT_TOKEN_TEST']
        os.environ['MONGODB_URL_CON'] = os.environ['MONGODB_URL_CON_TEST']

    token = os.environ['BOT_TOKEN']
    db_con_string = os.environ['MONGODB_URL_CON']

    from mongoengine import connect
    connect(host=os.environ['MONGODB_URL_CON'])

    updater = Updater(token=token)
    dispatcher = updater.dispatcher
    logger = logging.getLogger(__name__)
    logger.addHandler(logging.StreamHandler())

    GoToGymTask(updater, logger).run()
