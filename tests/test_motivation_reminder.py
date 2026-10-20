"""Tests for the daily motivation reminder.

The send time and the quote are derived from the date, so these are pure like the
schedule tests: no network, no database, no running scheduler, and every "now" is a
fixed instant passed in explicitly.
"""
import logging
import unittest
from datetime import date, datetime, time, timedelta

import pytz
from telegram.ext import Updater

from gym_bot_app.quotes import QUOTE_LIST, format_quote, quote_of_the_day
from gym_bot_app.tasks import GoToGymTask, MotivationReminderTask, WentToGymTask

# Well-formed but fake -- Bot() only validates the token's shape, it never calls out.
FAKE_TOKEN = '123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'

TZ = pytz.timezone('Asia/Jerusalem')

WINDOW_START = time(hour=9, minute=30)
WINDOW_END = time(hour=20, minute=30)

DAY = date(2026, 8, 2)


def days(start, count):
    return [start + timedelta(days=i) for i in range(count)]


def new_task():
    """A task on its own Updater, so jobs never leak between tests."""
    return MotivationReminderTask(updater=Updater(token=FAKE_TOKEN), logger=logging.getLogger('test'))


class TestSendTime(unittest.TestCase):

    def setUp(self):
        self.task = new_task()

    def test_window_is_between_the_first_and_last_reminders(self):
        self.assertEqual(self.task.window_start, GoToGymTask.DEFAULT_TARGET_TIME)
        self.assertEqual(self.task.window_end, WentToGymTask.DEFAULT_TARGET_TIME)

    def test_send_time_is_inside_the_window_all_year(self):
        """2026 covers both of Israel's daylight-saving changes (27/3 and 25/10)."""
        for day in days(date(2026, 1, 1), 365):
            with self.subTest(day=day):
                send_time = self.task.send_time_for(day).astimezone(TZ)
                self.assertEqual(send_time.date(), day)
                self.assertTrue(WINDOW_START <= send_time.time() <= WINDOW_END,
                                'sent at %s' % send_time)

    def test_send_time_is_aware_and_in_the_local_offset(self):
        """A naive or UTC-offset datetime would make run_once fire hours off."""
        for day in (date(2026, 1, 15), date(2026, 7, 15)):  # winter and summer offsets
            with self.subTest(day=day):
                send_time = self.task.send_time_for(day)
                self.assertIsNotNone(send_time.tzinfo)
                self.assertEqual(send_time.utcoffset(),
                                 TZ.localize(datetime.combine(day, time(hour=12))).utcoffset())

    def test_send_time_is_the_same_on_every_call(self):
        """What makes a restart plan the same send again."""
        self.assertEqual(self.task.send_time_for(DAY), new_task().send_time_for(DAY))

    def test_send_time_changes_between_days(self):
        times_of_day = {self.task.send_time_for(day).time() for day in days(DAY, 30)}
        self.assertGreater(len(times_of_day), 25)


class TestPlanDay(unittest.TestCase):

    def setUp(self):
        self.task = new_task()
        self.send_time = self.task.send_time_for(DAY)

    def scheduled_fire_time(self):
        trigger = self.task.send_job.job.trigger
        return trigger.get_next_fire_time(None, self.send_time - timedelta(hours=1))

    def test_plans_the_send_when_it_is_still_ahead(self):
        now = self.send_time - timedelta(minutes=1)
        self.assertEqual(self.task.plan_day(now=now), self.send_time)
        self.assertEqual(self.scheduled_fire_time(), self.send_time)

    def test_planning_after_midnight_targets_the_new_day(self):
        now = TZ.localize(datetime.combine(DAY, MotivationReminderTask.DEFAULT_TARGET_TIME))
        self.assertEqual(self.task.plan_day(now=now), self.send_time)

    def test_skips_the_day_when_the_send_already_passed(self):
        """A restart after today's quote went out must not send it again."""
        now = self.send_time + timedelta(seconds=1)
        self.assertIsNone(self.task.plan_day(now=now))
        self.assertIsNone(self.task.send_job)

    def test_does_not_plan_the_same_day_twice(self):
        """Startup and the daily planning job both plan; only one send may come of it."""
        now = self.send_time - timedelta(hours=1)
        self.task.plan_day(now=now)
        first_job = self.task.send_job

        self.assertIsNone(self.task.plan_day(now=now + timedelta(minutes=5)))
        self.assertIs(self.task.send_job, first_job)
        sends = [job for job in self.task.updater.job_queue.jobs()
                 if job.name == 'MotivationReminderTaskSend']
        self.assertEqual(len(sends), 1)

    def test_plans_again_the_next_day(self):
        self.task.plan_day(now=self.send_time - timedelta(hours=1))
        tomorrow = DAY + timedelta(days=1)
        now = TZ.localize(datetime.combine(tomorrow, MotivationReminderTask.DEFAULT_TARGET_TIME))
        self.assertEqual(self.task.plan_day(now=now), self.task.send_time_for(tomorrow))


class TestQuoteOfTheDay(unittest.TestCase):

    def test_same_day_gets_the_same_quote(self):
        self.assertIs(quote_of_the_day(DAY), quote_of_the_day(DAY))

    def test_every_quote_is_used_once_per_cycle(self):
        cycle_length = len(QUOTE_LIST)
        first_day_of_a_cycle = date.fromordinal((DAY.toordinal() // cycle_length + 1) * cycle_length)
        for cycle in range(20):
            start = first_day_of_a_cycle + timedelta(days=cycle * cycle_length)
            with self.subTest(cycle_start=start):
                used = [id(quote_of_the_day(day)) for day in days(start, cycle_length)]
                self.assertEqual(sorted(used), sorted(id(quote) for quote in QUOTE_LIST))

    def test_never_the_same_quote_two_days_in_a_row(self):
        """Including where one cycle ends and the next begins."""
        quotes = [quote_of_the_day(day) for day in days(date(2026, 1, 1), 3 * 365)]
        for yesterday, today in zip(quotes, quotes[1:]):
            self.assertIsNot(yesterday, today)

    def test_motivation_message_contains_the_quote_of_the_day(self):
        msg = new_task().get_motivation_msg(DAY)
        self.assertIn('מוטיבציה יומית', msg)
        self.assertIn(format_quote(quote_of_the_day(DAY)), msg)


if __name__ == '__main__':
    unittest.main()
