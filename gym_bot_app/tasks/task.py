# encoding: utf-8
from __future__ import unicode_literals

import threading
from datetime import datetime, timedelta

from gym_bot_app.utils import number_of_days_until_next_day


class Task(object):
    """Telegram gym bot abstract task class.

    updater(telegram.ext.Updater): bots' Updater instance.
    logger(logging.logger): logger to write to.

    """
    def __init__(self, updater, logger):
        self.updater = updater
        self.logger = logger

    def get_start_time(self):
        """Get the start time of the task.

        Returns:
            int. number of seconds untill the start time.

        """
        raise NotImplementedError('Not implemented start time method.')

    def _execute(self, *args, **kwargs):
        """Task execution implementation.

        Will be used once it reached the start time.

        """
        raise NotImplementedError('Not implemented execute method.')

    def start(self, *args, **kwargs):
        """Start the task.

        Calculate the start time and waits until reached in order to run the _execute method.

        Raises:
            RuntimeError. start time already passed.

        """
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
        """Calculate the number of seconds until the next occur of the target day and time.

        Args:
            target_day_name(str): name of the target day.
            target_time(time.time): target time of the day.

        Returns.
            int. number of seconds until the given day and time.

        """
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
        """Calculate the number of seconds until the next occur of the given time.

        If the time already passed (in the current day), targeting time of the next day.

        Args:
            target_time(time.time): target time for calculation.

        Returns:
            int. number of seconds until the given time.

        """
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
