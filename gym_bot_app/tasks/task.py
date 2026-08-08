import os
from datetime import datetime, time

import pytz

# APScheduler 3.6.3 (the version python-telegram-bot 13.7 depends on) accepts ONLY
# pytz timezones. Passing a zoneinfo.ZoneInfo raises
#     TypeError: Only timezones from the pytz library are supported
# so this must stay pytz. pytz is already a pinned dependency.
#
# The timezone comes from the TZ environment variable so the container's TZ setting is
# the single source of truth, defaulting to the bot's home timezone.
SCHEDULE_TIMEZONE = pytz.timezone(os.getenv('TZ', 'Asia/Jerusalem'))

# APScheduler's cron `day_of_week` is Monday=0 .. Sunday=6.
#
# WARNING: this is NOT the same ordering as gym_bot_app.DAYS_NAME, which starts on
# Sunday. DAYS_NAME.index('Saturday') is 6, which as a cron value means SUNDAY -- the
# weekly task would fire a day late. Keep this table separate and explicit.
#
# A literal table is used rather than time.strptime(name, '%A') because strptime's
# weekday names are locale-dependent.
CRON_DAY_OF_WEEK = {
    'monday': 0,
    'tuesday': 1,
    'wednesday': 2,
    'thursday': 3,
    'friday': 4,
    'saturday': 5,
    'sunday': 6,
}

EVERY_DAY = tuple(range(7))


def cron_day_of_week(day_name):
    """Translate an English weekday name into APScheduler's cron numbering.

    Args:
        day_name(str): English weekday name, e.g. 'Saturday'.

    Returns:
        int. the day in APScheduler cron numbering (Monday=0 .. Sunday=6).

    Raises:
        ValueError. the given name is not a weekday.

    """
    try:
        return CRON_DAY_OF_WEEK[day_name.strip().lower()]
    except (AttributeError, KeyError):
        raise ValueError('Unknown weekday name: {!r}'.format(day_name))


class Task(object):
    """Telegram gym bot abstract task class.

    A task is a recurring job that runs at a fixed local wall-clock time. Tasks are
    registered on the bot's job queue (APScheduler, shipped with python-telegram-bot)
    so the schedule is anchored to a real timezone and therefore survives daylight
    saving transitions -- 09:00 stays 09:00 local across the October change.

    updater(telegram.ext.Updater): bots' Updater instance.
    logger(logging.logger): logger to write to.

    """
    def __init__(self, updater, logger):
        self.updater = updater
        self.logger = logger
        self.job = None

    @property
    def target_days(self):
        """Days of the week the task runs on, in APScheduler cron numbering.

        Returns:
            tuple. of int, Monday=0 .. Sunday=6. Defaults to every day.

        """
        return EVERY_DAY

    def execute(self, *args, **kwargs):
        """Task execution implementation.

        Will be used once it reached the target time.

        """
        raise NotImplementedError('Not implemented execute method.')

    def _job_callback(self, context):
        """Job queue entry point.

        The job queue calls back with a CallbackContext, while execute() is wrapped by
        run_for_all_groups and receives the group as its argument, so the context is
        deliberately dropped here.

        """
        self.execute()

    def start(self, *args, **kwargs):
        """Register the task on the bot's job queue.

        Returns:
            Task. self, so callers can collect the started tasks.

        """
        self.logger.info('Task %s', self.__class__.__name__)

        # Only tzinfo is read off this object by run_daily (it becomes the cron
        # trigger's timezone), so self.target_time itself stays naive -- the /trained
        # command compares it against a naive datetime.now().time().
        target_time = time(hour=self.target_time.hour,
                           minute=self.target_time.minute,
                           second=self.target_time.second,
                           tzinfo=SCHEDULE_TIMEZONE)

        self.job = self.updater.job_queue.run_daily(callback=self._job_callback,
                                                    time=target_time,
                                                    days=self.target_days,
                                                    name=self.__class__.__name__)

        self.logger.info('Scheduled task %s at %s %s on days %s, next run %s',
                         self.__class__.__name__,
                         self.target_time,
                         SCHEDULE_TIMEZONE,
                         self.target_days,
                         self.next_run_time)

        return self

    @property
    def next_run_time(self):
        """Next time the task is scheduled to run, in the schedule timezone.

        Returns:
            datetime | None. None if the task was never started.

        """
        if self.job is None:
            return None

        scheduler_job = self.job.job
        next_run_time = getattr(scheduler_job, 'next_run_time', None)

        if next_run_time is None:
            # Tasks are registered before start_polling() starts the job queue, so at
            # startup the job is still pending and the scheduler has not assigned it a
            # run time yet. Ask the trigger directly, otherwise the schedule logged at
            # boot -- the thing that proves the schedule is right -- would be empty.
            trigger = getattr(scheduler_job, 'trigger', None)
            if trigger is None:
                return None
            next_run_time = trigger.get_next_fire_time(None, datetime.now(SCHEDULE_TIMEZONE))

        if next_run_time is None:
            return None

        return next_run_time.astimezone(SCHEDULE_TIMEZONE)
