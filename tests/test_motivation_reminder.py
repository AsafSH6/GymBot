"""Tests for the daily motivation reminder.

The send time and the quote are derived from the date, so these are pure like the
schedule tests: no network, no running scheduler, and every "now" is a fixed instant
passed in explicitly. The personal sentences of the groups are read from mongomock, an
in-memory MongoDB, or from TEST_MONGODB_URL if set (see tests.connect_test_db).
"""
import logging
import unittest
from datetime import date, datetime, time, timedelta
from unittest import mock

import pytz
from telegram import Bot
from telegram.ext import Updater
from telegram.utils.helpers import DEFAULT_NONE

from gym_bot_app.models import Group, PersonalMotivationQuote, Trainee
from gym_bot_app.quotes import QUOTE_LIST, format_quote, quote_of_the_day
from gym_bot_app.tasks import GoToGymTask, MotivationReminderTask, WentToGymTask
from tests import connect_test_db, disconnect_test_db

# Well-formed but fake -- Bot() only validates the token's shape, it never calls out.
FAKE_TOKEN = '123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'

TZ = pytz.timezone('Asia/Jerusalem')

WINDOW_START = time(hour=9, minute=30)
WINDOW_END = time(hour=20, minute=30)

DAY = date(2026, 8, 2)

GROUP_ID = '-100'
OTHER_GROUP_ID = '-200'


setUpModule = connect_test_db
tearDownModule = disconnect_test_db


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


class TestPersonalQuotes(unittest.TestCase):
    """Groups with personal sentences get one of them on part of the days."""

    def setUp(self):
        for model in (Group, PersonalMotivationQuote, Trainee):
            model.objects.delete()

        self.task = new_task()
        self.group = Group.objects.create(id=GROUP_ID)
        self.other_group = Group.objects.create(id=OTHER_GROUP_ID)

    @staticmethod
    def set_sentence(group, trainee_id, first_name, text):
        trainee = Trainee.objects.get(id=trainee_id) or Trainee.objects.create(id=trainee_id, first_name=first_name)
        PersonalMotivationQuote(group=group.pk, trainee=trainee.pk, text=text).save()

    def picks(self, group, count=400):
        return [self.task.pick_quote(day, group) for day in days(DAY, count)]

    def test_group_without_sentences_gets_the_quote_of_the_day(self):
        self.set_sentence(self.other_group, '1', 'Arnold', 'Not in this group')

        with mock.patch.object(MotivationReminderTask, 'PERSONAL_QUOTE_CHANCE', 1):
            for day in days(DAY, 30):
                self.assertIs(self.task.pick_quote(day, self.group), quote_of_the_day(day))

    def test_personal_sentence_is_signed_with_the_name_of_who_set_it(self):
        self.set_sentence(self.group, '1', 'Arnold', 'Never skip leg day')

        with mock.patch.object(MotivationReminderTask, 'PERSONAL_QUOTE_CHANCE', 1):
            msg = self.task.get_motivation_msg(DAY, self.group)

        self.assertIn('מוטיבציה יומית', msg)
        self.assertIn('"Never skip leg day", Arnold', msg)

    def test_without_the_chance_every_day_gets_the_quote_of_the_day(self):
        self.set_sentence(self.group, '1', 'Arnold', 'Never skip leg day')

        with mock.patch.object(MotivationReminderTask, 'PERSONAL_QUOTE_CHANCE', 0):
            for day in days(DAY, 30):
                self.assertIs(self.task.pick_quote(day, self.group), quote_of_the_day(day))

    def test_personal_sentences_are_sent_on_about_their_chance_of_the_days(self):
        self.set_sentence(self.group, '1', 'Arnold', 'Never skip leg day')
        self.set_sentence(self.group, '2', 'Ronnie', 'Yeah buddy')

        picks = self.picks(self.group)

        personal_share = sum(quote['author'] in ('Arnold', 'Ronnie') for quote in picks) / len(picks)
        self.assertAlmostEqual(personal_share, MotivationReminderTask.PERSONAL_QUOTE_CHANCE, delta=0.1)

    def test_every_personal_sentence_of_the_group_gets_sent(self):
        sentences = {'1': 'Never skip leg day', '2': 'Yeah buddy', '3': 'Light weight baby'}
        for trainee_id, text in sentences.items():
            self.set_sentence(self.group, trainee_id, 'Trainee' + trainee_id, text)
        self.set_sentence(self.other_group, '4', 'Other', 'Not in this group')

        sent = {quote['text'] for quote in self.picks(self.group)}

        self.assertTrue(set(sentences.values()) <= sent)
        self.assertNotIn('Not in this group', sent)

    def test_same_day_and_group_get_the_same_quote(self):
        """A restart, or running the task again via /admin, sends the same quote."""
        self.set_sentence(self.group, '1', 'Arnold', 'Never skip leg day')
        self.set_sentence(self.group, '2', 'Ronnie', 'Yeah buddy')

        self.assertEqual(self.picks(self.group, count=60), self.picks(self.group, count=60))

    def test_groups_get_their_own_quote(self):
        self.set_sentence(self.group, '1', 'Arnold', 'Never skip leg day')
        self.set_sentence(self.other_group, '2', 'Ronnie', 'Yeah buddy')

        self.assertNotEqual(self.picks(self.group, count=60), self.picks(self.other_group, count=60))

    def test_sends_each_group_its_quote_as_plain_text(self):
        self.set_sentence(self.group, '1', 'Arnold', 'Never skip leg day')
        bot = mock.create_autospec(Bot, instance=True)
        self.task.updater.bot = bot

        with mock.patch.object(MotivationReminderTask, 'PERSONAL_QUOTE_CHANCE', 1):
            self.task.execute()

        today = datetime.now(TZ).date()
        sent = {call.kwargs['chat_id']: call.kwargs for call in bot.send_message.call_args_list}
        self.assertEqual({chat_id: kwargs['text'] for chat_id, kwargs in sent.items()}, {
            GROUP_ID: MotivationReminderTask.MOTIVATION_MSG.format(quote='"Never skip leg day", Arnold'),
            OTHER_GROUP_ID: MotivationReminderTask.MOTIVATION_MSG.format(quote=format_quote(quote_of_the_day(today))),
        })
        for kwargs in sent.values():
            self.assertIs(kwargs['disable_web_page_preview'], True)
            self.assertIn(kwargs.get('parse_mode'), (None, DEFAULT_NONE))


if __name__ == '__main__':
    unittest.main()
