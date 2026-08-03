"""Schedule tests for the four recurring tasks.

These exist because the tasks used to re-arm themselves by adding a fixed 24 hours to
the previous run, which silently shifted every message by an hour at the October
daylight-saving change. They now run on the bot's job queue, anchored to a real
timezone, and these tests pin that behaviour.

They are pure: no network, no database, no running scheduler and no dependency on the
wall clock. Every assertion is computed from the job's cron trigger against a fixed
reference instant.
"""
import logging
import unittest
from datetime import datetime, time

import pytz
from telegram.ext import Updater

from gym_bot_app import DAYS_NAME
from gym_bot_app.tasks import (DidNotTrainUpdaterTask,
                               GoToGymTask,
                               NewWeekSelectDaysTask,
                               WentToGymTask)
from gym_bot_app.tasks.task import EVERY_DAY, SCHEDULE_TIMEZONE, cron_day_of_week

# Well-formed but fake -- Bot() only validates the token's shape, it never calls out.
FAKE_TOKEN = '123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'

TZ = pytz.timezone('Asia/Jerusalem')

# A fixed instant, so these tests never depend on when they are run.
REFERENCE = TZ.localize(datetime(2026, 8, 2, 12, 0, 0))

SATURDAY = 5

EXPECTED_SCHEDULE = {
    GoToGymTask: (time(hour=9, minute=0), EVERY_DAY),
    WentToGymTask: (time(hour=21, minute=0), EVERY_DAY),
    NewWeekSelectDaysTask: (time(hour=21, minute=30), (SATURDAY, )),
    DidNotTrainUpdaterTask: (time(hour=23, minute=55), EVERY_DAY),
}


class ScheduleTestCase(unittest.TestCase):
    """Base fixture: a real Updater with a fake token, and all four tasks started."""

    @classmethod
    def setUpClass(cls):
        cls.updater = Updater(token=FAKE_TOKEN)
        logger = logging.getLogger('test')
        cls.tasks = {task_cls: task_cls(updater=cls.updater, logger=logger).start()
                     for task_cls in EXPECTED_SCHEDULE}

    def next_fires(self, task_cls, count=1, after=REFERENCE):
        """Next `count` fire times of a task, in Asia/Jerusalem."""
        trigger = self.tasks[task_cls].job.job.trigger
        fires, previous, current = [], None, after
        for _ in range(count):
            fire = trigger.get_next_fire_time(previous, current)
            self.assertIsNotNone(fire, 'trigger produced no next fire time')
            fires.append(fire.astimezone(TZ))
            previous, current = fire, fires[-1]
        return fires


class TestTargetTimes(ScheduleTestCase):

    def test_every_task_fires_at_its_local_target_time(self):
        for task_cls, (expected_time, _) in EXPECTED_SCHEDULE.items():
            with self.subTest(task=task_cls.__name__):
                fire = self.next_fires(task_cls)[0]
                self.assertEqual((fire.hour, fire.minute),
                                 (expected_time.hour, expected_time.minute))

    def test_daily_tasks_fire_on_consecutive_days(self):
        for task_cls, (_, days) in EXPECTED_SCHEDULE.items():
            if days != EVERY_DAY:
                continue
            with self.subTest(task=task_cls.__name__):
                fires = self.next_fires(task_cls, count=3)
                gaps = {(b.date() - a.date()).days for a, b in zip(fires, fires[1:])}
                self.assertEqual(gaps, {1})

    def test_registered_days_match_expectation(self):
        for task_cls, (_, expected_days) in EXPECTED_SCHEDULE.items():
            with self.subTest(task=task_cls.__name__):
                self.assertEqual(tuple(self.tasks[task_cls].target_days), expected_days)


class TestWeeklyTask(ScheduleTestCase):

    def test_new_week_task_only_ever_fires_on_saturday(self):
        fires = self.next_fires(NewWeekSelectDaysTask, count=4)
        self.assertEqual({fire.strftime('%A') for fire in fires}, {'Saturday'})
        gaps = {(b.date() - a.date()).days for a, b in zip(fires, fires[1:])}
        self.assertEqual(gaps, {7})

    def test_cron_numbering_is_not_days_name_numbering(self):
        """Regression guard for the weekday-ordering trap.

        gym_bot_app.DAYS_NAME starts on Sunday, APScheduler's cron starts on Monday.
        Using DAYS_NAME.index('Saturday') as a cron value would schedule the weekly
        task on Sunday.
        """
        self.assertEqual(cron_day_of_week('Saturday'), SATURDAY)
        self.assertEqual(DAYS_NAME.index('Saturday'), 6)
        self.assertNotEqual(cron_day_of_week('Saturday'), DAYS_NAME.index('Saturday'))

    def test_unknown_weekday_name_is_rejected(self):
        with self.assertRaises(ValueError):
            cron_day_of_week('Caturday')


class TestDaylightSaving(ScheduleTestCase):
    """The bug these tasks were rewritten to fix."""

    # A window that straddles Israel's autumn transition (last Sunday of October).
    WINDOW_START = TZ.localize(datetime(2026, 10, 20, 12, 0, 0))

    def test_target_time_stays_constant_in_local_time_across_the_transition(self):
        fires = self.next_fires(GoToGymTask, count=10, after=self.WINDOW_START)
        self.assertTrue(all(fire.hour == 9 and fire.minute == 0 for fire in fires),
                        'the local time drifted: %s' % [str(f) for f in fires])

    def test_the_window_actually_contains_a_transition(self):
        """Stops the test above from silently passing on a window with no DST change."""
        fires = self.next_fires(GoToGymTask, count=10, after=self.WINDOW_START)
        offsets = {fire.utcoffset() for fire in fires}
        self.assertEqual(len(offsets), 2,
                         'expected the UTC offset to change exactly once, got %s' % offsets)


class TestTrainedCommandContract(ScheduleTestCase):
    """`/trained` compares these attributes against a naive datetime.now()."""

    def test_target_time_is_naive(self):
        for task_cls in EXPECTED_SCHEDULE:
            with self.subTest(task=task_cls.__name__):
                self.assertIsNone(self.tasks[task_cls].target_time.tzinfo)

    def test_target_day_is_still_an_english_day_name(self):
        self.assertIn(self.tasks[NewWeekSelectDaysTask].target_day, DAYS_NAME)

    def test_naive_comparison_used_by_trained_command_still_works(self):
        task = self.tasks[NewWeekSelectDaysTask]
        # The exact expression from commands/trained.py.
        self.assertIsInstance(datetime.now().time() > task.target_time, bool)


class TestScheduleTimezone(unittest.TestCase):

    def test_schedule_timezone_is_a_pytz_timezone(self):
        """APScheduler 3.6.3 rejects anything that is not pytz.

        A zoneinfo.ZoneInfo raises "Only timezones from the pytz library are
        supported" when the job is registered.
        """
        self.assertTrue(hasattr(SCHEDULE_TIMEZONE, 'localize'))
        self.assertTrue(hasattr(SCHEDULE_TIMEZONE, 'normalize'))


if __name__ == '__main__':
    unittest.main()
