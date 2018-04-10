# encoding: utf-8
from __future__ import unicode_literals

import threading
from datetime import datetime, timedelta

from gym_bot_app.utils import number_of_days_until_next_day


class Task(object):
    def __init__(self, dispatcher, updater, logger):
        self.dispatcher = dispatcher
        self.updater = updater
        self.logger = logger

    def get_start_time(self):
        raise NotImplementedError('Not implemented start time method.')

    def _execute(self, *args, **kwargs):
        raise NotImplementedError('Not implemented execute method.')

    def start(self, *args, **kwargs):
        self.logger.info('task: %s', self.__class__.__name__)
        start_time = self.get_start_time()
        self.logger.info('request task time is in %s seconds', start_time)
        if start_time < 0:
            self.logger.error('start time already passed')
            raise RuntimeError('%s start time already passed' % self.__class__.__name__)

        threading.Timer(start_time,
                        self._execute,
                        args=args,
                        kwargs=kwargs).start()
        self.logger.info('started task %s', self.__class__.__name__)

    def _seconds_until_day_and_time(self, target_day_name, target_time):
        self.logger.info('requested target day is %s and time is %s', target_day_name, target_time)
        now = datetime.today()
        days_until_next_target_day = number_of_days_until_next_day(target_day_name)

        target_datetime = now.replace(hour=target_time.hour,
                                      minute=target_time.minute,
                                      second=target_time.second,
                                      microsecond=target_time.microsecond)

        # if today is the requested day and the target time already passed.
        if days_until_next_target_day is 0 and now.time() > target_time:
            self.logger.info('today is the requested day but the time already passed, targeting time for next week')
            target_datetime += timedelta(weeks=1)
        else:
            self.logger.info('number of days left until the target day is %s', days_until_next_target_day)
            target_datetime += timedelta(days=days_until_next_target_day)

        return (target_datetime - now).total_seconds()

    def _seconds_until_time(self, target_time):
        self.logger.info('requested target time is %s', target_time)
        now = datetime.today()
        target_datetime = now.replace(hour=target_time.hour,
                                      minute=target_time.minute,
                                      second=target_time.second)
        if now > target_datetime:  # time already passed- move to the next day.
            self.logger.info('time already passed, targeting time for tomorrow')
            target_datetime += timedelta(days=1)
        else:
            self.logger.info('time did not pass, targeting time for today')
        self.logger.info('requested target datetime is %s', target_datetime)

        return (target_datetime - now).total_seconds()
