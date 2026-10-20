import random
from datetime import datetime, time, timedelta

from gym_bot_app import MUSCLE_EMOJI
from gym_bot_app.models import Group
from gym_bot_app.quotes import format_quote, quote_of_the_day
from gym_bot_app.tasks.task import Task, SCHEDULE_TIMEZONE
from gym_bot_app.tasks.go_to_gym import GoToGymTask
from gym_bot_app.tasks.went_to_gym import WentToGymTask
from gym_bot_app.decorators import run_for_all_groups


class MotivationReminderTask(Task):
    """Telegram gym bot motivation reminder task.

    Sends the quote of the day to all groups once a day, at a random time between the
    go to gym reminder and the went to gym question.

    The daily job at target_time only plans the day: it schedules a one-off send at the
    day's random time. Both that time and the quote are derived from the date, so a
    restart in the middle of the day plans exactly the same send again -- nothing has to
    survive a redeploy, and a group never gets two quotes in one day.

    """
    DEFAULT_TARGET_TIME = time(hour=0, minute=5, second=0, microsecond=0)
    DEFAULT_WINDOW_START = GoToGymTask.DEFAULT_TARGET_TIME
    DEFAULT_WINDOW_END = WentToGymTask.DEFAULT_TARGET_TIME
    WINDOW_MARGIN = timedelta(minutes=30)  # Keeps the quote away from the reminders themselves.

    MOTIVATION_MSG = MUSCLE_EMOJI + ' מוטיבציה יומית\n{quote}'

    def __init__(self, target_time=None, window_start=None, window_end=None, *args, **kwargs):
        super(MotivationReminderTask, self).__init__(*args, **kwargs)
        self.target_time = target_time or self.DEFAULT_TARGET_TIME
        self.window_start = window_start or self.DEFAULT_WINDOW_START
        self.window_end = window_end or self.DEFAULT_WINDOW_END
        self.send_job = None
        self._planned_day = None

    def start(self, *args, **kwargs):
        """Override method to also plan today.

        The daily planning job first runs tonight, so without this a restart during the
        day would skip today's quote.

        """
        super(MotivationReminderTask, self).start(*args, **kwargs)
        self.plan_day()
        return self

    def _job_callback(self, context):
        """Daily planning job: schedule today's send instead of sending now."""
        self.plan_day()

    def _send_callback(self, context):
        self.execute()

    def send_time_for(self, day):
        """Time the quote of the given day is sent at.

        Random within the window, but seeded by the date so it is the same on every call.

        Args:
            day(datetime.date): day to get the send time of.

        Returns:
            datetime. timezone-aware, in the schedule timezone.

        """
        # Must be localized: run_once hands the datetime straight to the scheduler, which
        # reads a naive one as UTC -- the quote would arrive two or three hours off.
        start = SCHEDULE_TIMEZONE.localize(datetime.combine(day, self.window_start)) + self.WINDOW_MARGIN
        end = SCHEDULE_TIMEZONE.localize(datetime.combine(day, self.window_end)) - self.WINDOW_MARGIN

        rng = random.Random(day.isoformat())
        offset = timedelta(seconds=rng.randint(0, int((end - start).total_seconds())))
        return start + offset

    def plan_day(self, now=None):
        """Schedule the send of the current day.

        Does nothing if the day was already planned, or its send time already passed.

        Args:
            now(datetime): timezone-aware current time. Defaults to now.

        Returns:
            datetime | None. the planned send time, None if nothing was scheduled.

        """
        now = now or datetime.now(SCHEDULE_TIMEZONE)
        day = now.astimezone(SCHEDULE_TIMEZONE).date()

        if day == self._planned_day:
            self.logger.debug('Motivation reminder of %s is already planned', day)
            return None

        send_time = self.send_time_for(day)
        if send_time <= now:
            self.logger.info('Motivation reminder of %s was due at %s, skipping it', day, send_time)
            return None

        self.send_job = self.updater.job_queue.run_once(callback=self._send_callback,
                                                        when=send_time,
                                                        name='{}Send'.format(self.__class__.__name__))
        self._planned_day = day
        self.logger.info('Planned motivation reminder of %s at %s', day, send_time)
        return send_time

    def get_motivation_msg(self, day):
        """Generate the motivation message of the given day.

        Args:
            day(datetime.date): day to generate the message of.

        Returns:
            str. motivation message with the quote of the day.

        """
        return self.MOTIVATION_MSG.format(quote=format_quote(quote_of_the_day(day)))

    @run_for_all_groups
    def execute(self, group: Group):
        """Override method to execute motivation reminder task.

        Sends the quote of the day to the given group chat.

        """
        self.logger.info('Executing motivation reminder task with %s', group)

        today = datetime.now(SCHEDULE_TIMEZONE).date()
        self.updater.bot.send_message(chat_id=group.id, text=self.get_motivation_msg(today))
