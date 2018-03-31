# encoding: utf-8
from __future__ import unicode_literals
import threading
from datetime import datetime, time, timedelta


def repeat(seconds_to_wait):
    def decorator(func):
        def wrapper(*args, **kwargs):
            threading.Timer(seconds_to_wait,
                            func,
                            args=args,
                            kwargs=kwargs).start()
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
        start_time = self.get_start_time()
        if start_time < 0:
            raise RuntimeError('%s start time already passed' % self.__class__.__name__)

        threading.Timer(start_time,
                        self.execute,
                        args=args,
                        kwargs=kwargs).start()
