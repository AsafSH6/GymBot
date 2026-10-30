import random
from datetime import datetime, time, timedelta

from gym_bot_app import MUSCLE_EMOJI
from gym_bot_app.models import Group, PersonalMotivationQuote
from gym_bot_app.quotes import format_quote, quote_of_the_day
from gym_bot_app.tasks.task import Task, SCHEDULE_TIMEZONE
from gym_bot_app.tasks.go_to_gym import GoToGymTask
from gym_bot_app.tasks.went_to_gym import WentToGymTask
from gym_bot_app.decorators import run_for_all_groups


class MotivationReminderTask(Task):
    """Telegram gym bot motivation reminder task.

    Sends a motivation quote to all groups once a day, at a random time between the go to
    gym reminder and the went to gym question. A group that has personal motivation
    sentences (see SetMotivationCommand) gets one of them on PERSONAL_QUOTE_CHANCE of the
    days, and the quote of the day otherwise.

    The daily job at target_time only plans the day: it schedules a one-off send at the
    day's random time. That time is derived from the date, and the quote from the date and
    the group, so a restart in the middle of the day plans exactly the same send again --
    nothing has to survive a redeploy, and a group never gets two quotes in one day.

    """
    DEFAULT_TARGET_TIME = time(hour=0, minute=5, second=0, microsecond=0)
    DEFAULT_WINDOW_START = GoToGymTask.DEFAULT_TARGET_TIME
    DEFAULT_WINDOW_END = WentToGymTask.DEFAULT_TARGET_TIME
    WINDOW_MARGIN = timedelta(minutes=30)  # Keeps the quote away from the reminders themselves.
    PERSONAL_QUOTE_CHANCE = 0.5  # Chance a group with personal sentences gets one of them instead of the quote of the day.

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

    def pick_quote(self, day, group):
        """Pick the quote the given group gets on the given day.

        One of the personal sentences of the group on PERSONAL_QUOTE_CHANCE of the days, if
        it has any, and the quote of the day otherwise. Seeded by the day and the group, so
        it is the same on every call as long as the sentences of the group stay the same.

        Args:
            day(datetime.date): day to pick the quote for.
            group(models.Group): group to pick the quote for.

        Returns:
            dict. quote in the form of the quotes of QUOTE_LIST.

        """
        rng = random.Random('{day} {group_id}'.format(day=day.isoformat(), group_id=group.id))
        if rng.random() < self.PERSONAL_QUOTE_CHANCE:
            # Ordered, so the seeded pick does not depend on the order the database returns them in.
            personal_quotes = list(PersonalMotivationQuote.objects(group=group.pk).order_by('trainee'))
            if personal_quotes:
                return rng.choice(personal_quotes).as_quote()

        return quote_of_the_day(day)

    def get_motivation_msg(self, day, group):
        """Generate the motivation message of the given day for the given group.

        Args:
            day(datetime.date): day to generate the message of.
            group(models.Group): group to generate the message for.

        Returns:
            str. motivation message with the quote the group gets on that day.

        """
        return self.MOTIVATION_MSG.format(quote=format_quote(self.pick_quote(day, group)))

    @run_for_all_groups
    def execute(self, group: Group):
        """Override method to execute motivation reminder task.

        Sends the quote the given group gets today to its chat.

        """
        self.logger.info('Executing motivation reminder task with %s', group)

        today = datetime.now(SCHEDULE_TIMEZONE).date()
        # Personal sentences are free text from trainees, so the message is sent as plain text, without previews.
        self.updater.bot.send_message(chat_id=group.id,
                                      text=self.get_motivation_msg(today, group),
                                      disable_web_page_preview=True)
