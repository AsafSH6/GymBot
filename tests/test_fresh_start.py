"""Tests for fresh start votes and trainee seasons.

They run against mongomock, an in-memory MongoDB (see requirements-test.txt), and against
a fixed clock, so they never depend on the database or on when they are run. Set
TEST_MONGODB_URL to run them against a real MongoDB instead. Every test wipes that
database, so its name must contain "test".

Handlers are driven with real telegram Updates, and the bot is an autospec of the real
telegram.Bot, so a call with a wrong method or argument name fails the test.
"""
import logging
import os
import threading
import time
import unittest
from datetime import datetime, timedelta
from unittest import mock

import mongomock
import pytz
from mongoengine import connect, disconnect
from mongoengine.connection import get_db
from telegram import Bot, Update
from pymongo.errors import ServerSelectionTimeoutError
from telegram.error import BadRequest, NetworkError, RetryAfter, TimedOut, Unauthorized
from telegram.ext import Updater

from gym_bot_app.commands import AdminCommand, MyStatisticsCommand, TrainedCommand
from gym_bot_app.commands.fresh_start import (CloseFreshStartVote, FreshStartCommand, RemindFreshStartVote,
                                              fresh_start_deadline)
from gym_bot_app.models import Admin, EXPEvent, FreshStartVote, Group, Level, Trainee, TrainingDayInfo
from gym_bot_app.utils import trainee_already_marked_training_date

# Well-formed but fake -- Bot() only validates the token's shape, it never calls out.
FAKE_TOKEN = '123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'

TZ = pytz.timezone('Asia/Jerusalem')

NOW = datetime(2026, 10, 20, 12, 0, 0)
SEASON_START = datetime(2026, 10, 15)
CLOSES_TONIGHT = datetime(2026, 10, 21)  # The midnight after NOW.
EXP_PER_TRAINING = 2

GROUP_ID = '-100'
OTHER_GROUP_ID = '-200'

MODELS = (Admin, EXPEvent, FreshStartVote, Group, Trainee, TrainingDayInfo)


class FrozenDatetime(datetime):
    """datetime whose now() and today() are always NOW."""

    @classmethod
    def now(cls, tz=None):
        return NOW

    @classmethod
    def today(cls):
        return NOW


def setUpModule():
    if os.getenv('TEST_MONGODB_URL'):
        connect(host=os.environ['TEST_MONGODB_URL'])
        db_name = get_db().name
        if 'test' not in db_name:
            disconnect()
            raise RuntimeError('Refusing to wipe {!r}: TEST_MONGODB_URL must name a test database'.format(db_name))
    else:
        connect('gymbot_test', mongo_client_class=mongomock.MongoClient)


def tearDownModule():
    disconnect()


def level_after(exp, level=None):
    """(number, exp) of the given level, level 1 by default, after gaining the given EXP."""
    level = Level(number=level.number, exp=level.exp) if level is not None else Level()
    level.gain_exp(exp=exp)
    return level.number, level.exp


def as_tuple(level):
    return level.number, level.exp


def level_of(document):
    return as_tuple(document.level)


def day(day_of_month, month=10):
    return datetime(2026, month, day_of_month)


def reload_trainee(trainee_id='1'):
    return Trainee.objects.get(id=trainee_id)


def reload_group(group_id=GROUP_ID):
    return Group.objects.get(id=group_id)


class DatabaseTestCase(unittest.TestCase):

    def setUp(self):
        for model in MODELS:
            model.objects.delete()

        for module in ('gym_bot_app.models', 'gym_bot_app.commands.fresh_start', 'gym_bot_app.commands.trained'):
            frozen_clock = mock.patch('{}.datetime'.format(module), FrozenDatetime)
            frozen_clock.start()
            self.addCleanup(frozen_clock.stop)

    @staticmethod
    def create_trainee(trainee_id='1', first_name='Arnold'):
        return Trainee.objects.create(id=trainee_id, first_name=first_name)

    @staticmethod
    def create_group(trainees, group_id=GROUP_ID):
        # Trainees join a group through add_trainee, which stores only their id, as in
        # production. Passing them to create() stores a full copy instead, which
        # Trainee.groups does not match.
        group = Group.objects.create(id=group_id)
        for trainee in trainees:
            group.add_trainee(trainee)
        return reload_group(group_id)

    @staticmethod
    def train(trainee, day_of_month, trained=True):
        return trainee.add_training_info(training_date=day(day_of_month).date(), trained=trained)


class TestFreshStartDeadline(unittest.TestCase):

    def test_closes_at_midnight_starting_the_day_after_tomorrow(self):
        self.assertEqual(fresh_start_deadline(datetime(2026, 10, 19, 10, 30)), datetime(2026, 10, 21))

    def test_is_always_a_midnight_between_24_and_48_hours_away(self):
        for hour in range(24):
            for minute in (0, 59):
                with self.subTest(hour=hour, minute=minute):
                    now = datetime(2026, 10, 19, hour, minute)
                    deadline = fresh_start_deadline(now)
                    self.assertEqual(deadline.time(), datetime.min.time())
                    self.assertGreaterEqual(deadline - now, timedelta(hours=24))
                    self.assertLessEqual(deadline - now, timedelta(hours=48))

    def test_crosses_month_and_year_ends(self):
        self.assertEqual(fresh_start_deadline(datetime(2026, 10, 31, 9)), datetime(2026, 11, 2))
        self.assertEqual(fresh_start_deadline(datetime(2026, 12, 30, 23, 59)), datetime(2027, 1, 1))


class TestSeasons(DatabaseTestCase):
    """A trainee who trained on the 13th, missed the 14th, started over on the 15th, then
    trained on the 15th, missed the 16th and trained on the 17th."""

    def setUp(self):
        super(TestSeasons, self).setUp()
        self.trainee = self.create_trainee()

        self.train(self.trainee, 13)
        self.train(self.trainee, 14, trained=False)
        self.old_season_level = Level(number=self.trainee.level.number, exp=self.trainee.level.exp)

        self.assertTrue(self.trainee.start_new_season(started_at=SEASON_START))

        self.train(self.trainee, 15)
        self.train(self.trainee, 16, trained=False)
        self.train(self.trainee, 17)

    def test_new_season_starts_from_level_1(self):
        trainee = reload_trainee()
        self.assertEqual(level_of(trainee), level_after(2 * EXP_PER_TRAINING))
        self.assertEqual((trainee.season_number, trainee.season_started_at), (2, SEASON_START))

    def test_past_season_keeps_its_level_and_training_days(self):
        past_season, = reload_trainee().past_seasons
        self.assertEqual((past_season.number, past_season.started_at, past_season.ended_at),
                         (1, None, SEASON_START))
        self.assertEqual(level_of(past_season), level_after(EXP_PER_TRAINING))
        self.assertEqual(self.trainee.count_trained_days_in_past_season(past_season), 1)

    def test_statistics_count_only_the_current_season(self):
        trained_days, missed_training_days, training_percentage, _ = reload_trainee().get_training_statistics()
        self.assertEqual((trained_days, missed_training_days, training_percentage), (2, 1, 67))

    def test_month_and_year_count_only_trained_days_of_the_current_season(self):
        trainee = reload_trainee()
        self.assertEqual(trainee.calculate_statistics_training_days_for_this_month(10), (2, 20, 10.0))
        self.assertEqual(trainee.calculate_statistics_training_days_for_this_year(2026)[0], 2)

    def test_months_before_the_season_count_nothing(self):
        TrainingDayInfo.objects.create(trainee=self.trainee.pk, date=day(10, month=9), trained=True)

        self.assertEqual(reload_trainee().calculate_statistics_training_days_for_this_month(9), (0, 30, 0))

    def test_missed_days_are_not_counted_as_trained_days(self):
        trainee = self.create_trainee('2', 'Ronnie')
        self.train(trainee, 13)
        self.train(trainee, 14, trained=False)

        self.assertEqual(trainee.calculate_statistics_training_days_for_this_month(10), (1, 20, 5.0))
        self.assertEqual(trainee.calculate_statistics_training_days_for_this_year(2026)[0], 1)

    def test_answers_from_a_past_season_still_count_as_answered(self):
        """Otherwise a trainee could answer about the same day twice and gain its EXP twice."""
        trainee = reload_trainee()
        self.assertTrue(trainee_already_marked_training_date(trainee=trainee, training_date=day(13).date()))
        with self.assertRaises(RuntimeError):
            self.train(trainee, 13)

    def test_late_answer_for_a_past_season_counts_in_that_season(self):
        _, leveled_up = self.train(reload_trainee(), 12)

        self.assertFalse(leveled_up)
        trainee = reload_trainee()
        self.assertEqual(level_of(trainee.past_seasons[0]), level_after(EXP_PER_TRAINING, self.old_season_level))
        self.assertEqual(level_of(trainee), level_after(2 * EXP_PER_TRAINING))
        self.assertEqual(trainee.count_trained_days_in_past_season(trainee.past_seasons[0]), 2)
        self.assertEqual(trainee.get_training_statistics()[0], 2)

    def test_starting_the_same_or_an_older_season_does_nothing(self):
        for started_at in (SEASON_START, SEASON_START - timedelta(days=1)):
            with self.subTest(started_at=started_at):
                trainee = reload_trainee()
                self.assertFalse(trainee.start_new_season(started_at=started_at))

                trainee = reload_trainee()
                self.assertEqual((trainee.season_number, trainee.season_started_at), (2, SEASON_START))
                self.assertEqual(len(trainee.past_seasons), 1)
                self.assertEqual(level_of(trainee), level_after(2 * EXP_PER_TRAINING))

    def test_undo_goes_back_and_keeps_the_exp_gained_since(self):
        reload_trainee().undo_season()

        trainee = reload_trainee()
        self.assertEqual(level_of(trainee), level_after(2 * EXP_PER_TRAINING, self.old_season_level))
        self.assertEqual((trainee.season_number, trainee.season_started_at), (1, None))
        self.assertEqual(len(trainee.past_seasons), 0)
        self.assertEqual(trainee.get_training_statistics()[:2], (3, 2))

    def test_third_season_and_undoing_both(self):
        third_season_start = day(18)
        self.assertTrue(reload_trainee().start_new_season(started_at=third_season_start))
        self.train(reload_trainee(), 18)

        trainee = reload_trainee()
        first, second = trainee.past_seasons
        self.assertEqual((first.number, first.started_at, first.ended_at), (1, None, SEASON_START))
        self.assertEqual((second.number, second.started_at, second.ended_at), (2, SEASON_START, third_season_start))
        self.assertEqual(level_of(second), level_after(2 * EXP_PER_TRAINING))
        self.assertEqual(trainee.count_trained_days_in_past_season(second), 2)
        self.assertEqual(trainee.get_training_statistics()[:2], (1, 0))

        reload_trainee().undo_season()
        trainee = reload_trainee()
        self.assertEqual((trainee.season_number, trainee.season_started_at), (2, SEASON_START))
        self.assertEqual(level_of(trainee), level_after(3 * EXP_PER_TRAINING))
        self.assertEqual(trainee.get_training_statistics()[:2], (3, 1))

        reload_trainee().undo_season()
        trainee = reload_trainee()
        self.assertEqual((trainee.season_number, trainee.season_started_at), (1, None))
        self.assertEqual(level_of(trainee), level_after(4 * EXP_PER_TRAINING))
        self.assertEqual(trainee.get_training_statistics()[:2], (4, 2))

    def test_inconsistent_exp_is_logged_and_never_goes_negative(self):
        trainee = reload_trainee()
        trainee.level = Level()  # Less than the training on day 17 gave.
        trainee.save()

        with self.assertLogs('gym_bot_app.models', level='WARNING'):
            self.assertTrue(reload_trainee().start_new_season(started_at=day(16)))
        trainee = reload_trainee()
        self.assertEqual(level_of(trainee.past_seasons[-1]), (1, 0))
        self.assertEqual(level_of(trainee), level_after(EXP_PER_TRAINING))

    def test_trainee_saved_before_seasons_existed_loads_as_season_1(self):
        Trainee._get_collection().insert_one({'_id': '3', 'first_name': 'Old', 'training_days': [],
                                              'level': {'number': 12, 'exp': 5}})

        trainee = reload_trainee('3')
        self.assertEqual((trainee.season_number, trainee.season_started_at, list(trainee.past_seasons)),
                         (1, None, []))
        self.assertEqual(level_of(trainee), (12, 5))
        self.assertTrue(trainee.start_new_season(started_at=SEASON_START))
        self.assertEqual(level_of(reload_trainee('3').past_seasons[0]), (12, 5))


class TestFreshStartVote(DatabaseTestCase):

    def setUp(self):
        super(TestFreshStartVote, self).setUp()
        self.arnold = self.create_trainee('1', 'Arnold')
        self.ronnie = self.create_trainee('2', 'Ronnie')
        self.train(self.arnold, 13)
        self.train(self.ronnie, 13)
        self.group = self.create_group(trainees=[self.arnold, self.ronnie])
        self.group.level = Level(number=3, exp=1)
        self.group.save()
        self.vote = FreshStartVote.objects.create(group=self.group.pk, executes_at=SEASON_START)

    def run_vote(self, *participants):
        for trainee in participants:
            self.vote.add_participant(trainee)
        self.assertTrue(self.vote.close())
        return self.vote.start_new_seasons()

    def test_participants_can_join_and_leave_an_open_vote(self):
        self.assertTrue(self.vote.add_participant(self.arnold))
        self.assertTrue(self.vote.add_participant(self.arnold))
        self.assertTrue(self.vote.add_participant(self.ronnie))
        self.assertEqual(FreshStartVote.objects.get(id=self.vote.id).participants, ['1', '2'])

        self.assertTrue(self.vote.remove_participant(self.ronnie))
        self.assertEqual(FreshStartVote.objects.get(id=self.vote.id).participants, ['1'])

    def test_vote_closes_once_and_cannot_be_joined_or_left_after(self):
        self.vote.add_participant(self.arnold)

        self.assertTrue(self.vote.close())
        self.assertEqual(self.vote.status, FreshStartVote.CLOSING)
        self.vote.start_new_seasons()
        self.assertEqual(FreshStartVote.objects.get(id=self.vote.id).status, FreshStartVote.DONE)
        self.assertFalse(self.vote.close())
        self.assertFalse(self.vote.add_participant(self.ronnie))
        self.assertFalse(self.vote.remove_participant(self.arnold))
        self.assertEqual(FreshStartVote.objects.get(id=self.vote.id).participants, ['1'])

    def test_vote_nobody_joined_is_cancelled(self):
        self.assertTrue(self.vote.close())
        self.assertEqual(FreshStartVote.objects.get(id=self.vote.id).status, FreshStartVote.CANCELLED)
        self.assertIsNone(FreshStartVote.objects.get_last_done(self.group))

    def test_cancelled_vote_does_not_close(self):
        self.assertTrue(self.vote.cancel())
        self.assertFalse(self.vote.cancel())
        self.assertIsNone(FreshStartVote.objects.get_pending(self.group))
        self.assertFalse(self.vote.close())

    def test_open_vote_is_marked_reminded_once(self):
        self.assertFalse(self.vote.reminded)
        self.assertTrue(self.vote.mark_reminded())
        self.assertTrue(FreshStartVote.objects.get(id=self.vote.id).reminded)
        self.assertFalse(self.vote.mark_reminded())

    def test_vote_saved_before_reminders_existed_can_be_marked_reminded(self):
        FreshStartVote._get_collection().update_one({'_id': self.vote.id}, {'$unset': {'reminded': ''}})
        self.assertNotIn('reminded', FreshStartVote._get_collection().find_one({'_id': self.vote.id}))

        vote = FreshStartVote.objects.get(id=self.vote.id)
        self.assertFalse(vote.reminded)
        self.assertTrue(vote.mark_reminded())
        self.assertFalse(vote.mark_reminded())

    def test_vote_that_is_not_open_is_never_marked_reminded(self):
        for status in (FreshStartVote.CLOSING, FreshStartVote.DONE, FreshStartVote.CANCELLED, FreshStartVote.UNDONE):
            FreshStartVote.objects.filter(id=self.vote.id).update_one(set__status=status)
            self.assertFalse(self.vote.mark_reminded())
            self.assertFalse(FreshStartVote.objects.get(id=self.vote.id).reminded)

    def test_only_participants_and_the_bot_start_over(self):
        self.assertEqual([trainee.id for trainee in self.run_vote(self.arnold)], ['1'])

        arnold = reload_trainee('1')
        ronnie = reload_trainee('2')
        self.assertEqual((arnold.season_number, level_of(arnold)), (2, (1, 0)))
        self.assertEqual((ronnie.season_number, level_of(ronnie)), (1, level_after(EXP_PER_TRAINING)))
        self.assertEqual(level_of(reload_group()), (1, 0))
        vote = FreshStartVote.objects.get(id=self.vote.id)
        self.assertEqual((vote.group_level.number, vote.group_level.exp), (3, 1))

    def test_reset_keeps_the_trainees_in_their_groups(self):
        self.create_group(trainees=[self.arnold], group_id=OTHER_GROUP_ID)
        self.run_vote(self.arnold)

        self.assertEqual({group.id for group in reload_trainee('1').groups}, {GROUP_ID, OTHER_GROUP_ID})
        self.assertEqual({trainee.id for trainee in reload_group().trainees}, {'1', '2'})

    def test_undo_restores_the_participants_and_the_bot(self):
        self.run_vote(self.arnold)
        self.train(reload_trainee('1'), 16)
        group = reload_group()
        group.level.gain_exp(exp=EXP_PER_TRAINING)  # As /trained does.
        group.save()

        self.assertEqual(FreshStartVote.objects.get_last_done(self.group), self.vote)
        undone_trainees = FreshStartVote.objects.get(id=self.vote.id).undo()

        arnold = reload_trainee('1')
        self.assertEqual([trainee.id for trainee in undone_trainees], ['1'])
        self.assertEqual((arnold.season_number, arnold.season_started_at, len(arnold.past_seasons)), (1, None, 0))
        self.assertEqual(level_of(arnold), level_after(2 * EXP_PER_TRAINING))
        self.assertEqual(level_of(reload_group()), level_after(EXP_PER_TRAINING, Level(number=3, exp=1)))
        self.assertEqual(FreshStartVote.objects.get(id=self.vote.id).status, FreshStartVote.UNDONE)
        self.assertIsNone(FreshStartVote.objects.get_last_done(self.group))

    def test_undo_leaves_trainees_who_started_over_again_since(self):
        self.run_vote(self.arnold, self.ronnie)
        reload_trainee('2').start_new_season(started_at=day(18))

        undone_trainees = FreshStartVote.objects.get(id=self.vote.id).undo()

        self.assertEqual([trainee.id for trainee in undone_trainees], ['1'])
        self.assertEqual(reload_trainee('1').season_number, 1)
        self.assertEqual(reload_trainee('2').season_number, 3)

    def test_trainings_recorded_before_a_late_reset_count_in_the_new_season(self):
        """The bot was down at midnight, and trainings of the new season came in first."""
        self.vote.add_participant(self.arnold)
        for trainee in (self.arnold, self.ronnie):
            self.train(reload_trainee(trainee.id), 15)
            self.train(reload_trainee(trainee.id), 16)
        group = reload_group()
        group.level = Level.from_total_exp(group.level.total_exp + 4 * EXP_PER_TRAINING)  # As /trained does.
        group.save()

        self.vote.close()
        self.vote.start_new_seasons()

        arnold = reload_trainee('1')
        self.assertEqual(level_of(arnold), level_after(2 * EXP_PER_TRAINING))
        self.assertEqual(arnold.get_training_statistics()[0], 2)
        self.assertEqual(level_of(arnold.past_seasons[0]), level_after(EXP_PER_TRAINING))
        self.assertEqual(level_of(reload_group()), (1, 0))
        self.assertEqual(as_tuple(FreshStartVote.objects.get(id=self.vote.id).group_level),
                         level_after(4 * EXP_PER_TRAINING, Level(number=3, exp=1)))

        FreshStartVote.objects.get(id=self.vote.id).undo()
        self.assertEqual(level_of(reload_trainee('1')), level_after(3 * EXP_PER_TRAINING))
        self.assertEqual(level_of(reload_group()), level_after(4 * EXP_PER_TRAINING, Level(number=3, exp=1)))

    def test_undo_restores_exactly_what_the_bot_had(self):
        """Not recalculated from the trainings, which would count members who joined since."""
        self.run_vote(self.arnold)
        newcomer = self.create_trainee('3', 'Newcomer')
        reload_group().add_trainee(newcomer)
        self.train(newcomer, 16)  # Reported in another group, this group gained nothing.

        FreshStartVote.objects.get(id=self.vote.id).undo()

        self.assertEqual(level_of(reload_group()), (3, 1))

    def test_closing_interrupted_by_a_crash_finishes_without_resetting_twice(self):
        self.vote.add_participant(self.arnold)
        self.vote.add_participant(self.ronnie)
        self.vote.close()

        start_new_season = Trainee.start_new_season

        def crash_on_ronnie(trainee, started_at):
            if trainee.id == '2':
                raise RuntimeError('crash')
            return start_new_season(trainee, started_at=started_at)

        with mock.patch.object(Trainee, 'start_new_season', crash_on_ronnie):
            with self.assertRaises(RuntimeError):
                FreshStartVote.objects.get(id=self.vote.id).start_new_seasons()

        with mock.patch.object(Group, 'save', side_effect=RuntimeError('crash')):
            with self.assertRaises(RuntimeError):
                FreshStartVote.objects.get(id=self.vote.id).start_new_seasons()

        vote = FreshStartVote.objects.get(id=self.vote.id)
        self.assertEqual(vote.status, FreshStartVote.CLOSING)
        self.assertEqual(list(FreshStartVote.objects.get_unfinished()), [vote])
        self.assertTrue(vote.close())
        self.assertEqual(sorted(trainee.id for trainee in vote.start_new_seasons()), ['1', '2'])

        for trainee_id in ('1', '2'):
            trainee = reload_trainee(trainee_id)
            self.assertEqual((trainee.season_number, len(trainee.past_seasons), level_of(trainee)), (2, 1, (1, 0)))
        self.assertEqual(level_of(reload_group()), (1, 0))
        vote = FreshStartVote.objects.get(id=self.vote.id)
        self.assertEqual((vote.status, as_tuple(vote.group_level)), (FreshStartVote.DONE, (3, 1)))

        vote.undo()
        self.assertEqual(level_of(reload_group()), (3, 1))
        self.assertEqual({reload_trainee(trainee_id).season_number for trainee_id in ('1', '2')}, {1})

    def test_crash_right_after_the_bot_reset_keeps_the_snapshot_from_before_it(self):
        self.vote.add_participant(self.arnold)
        self.vote.close()
        save_group = Group.save

        def save_then_crash(group, *args, **kwargs):
            save_group(group, *args, **kwargs)
            raise RuntimeError('crash')

        with mock.patch.object(Group, 'save', save_then_crash):
            with self.assertRaises(RuntimeError):
                FreshStartVote.objects.get(id=self.vote.id).start_new_seasons()
        self.assertEqual(level_of(reload_group()), (1, 0))

        vote = FreshStartVote.objects.get(id=self.vote.id)
        vote.close()
        vote.start_new_seasons()

        self.assertEqual(as_tuple(FreshStartVote.objects.get(id=self.vote.id).group_level), (3, 1))
        FreshStartVote.objects.get(id=self.vote.id).undo()
        self.assertEqual(level_of(reload_group()), (3, 1))

    def test_crash_after_the_bot_reset_does_not_reset_it_again(self):
        self.vote.add_participant(self.arnold)
        self.vote.close()
        save_vote = FreshStartVote.save

        def crash_when_done(vote, *args, **kwargs):
            if vote.status == FreshStartVote.DONE:
                raise RuntimeError('crash')
            return save_vote(vote, *args, **kwargs)

        with mock.patch.object(FreshStartVote, 'save', crash_when_done):
            with self.assertRaises(RuntimeError):
                FreshStartVote.objects.get(id=self.vote.id).start_new_seasons()
        group = reload_group()
        group.level.gain_exp(exp=EXP_PER_TRAINING)  # The bot kept running before it restarted.
        group.save()

        vote = FreshStartVote.objects.get(id=self.vote.id)
        self.assertEqual(vote.status, FreshStartVote.CLOSING)
        vote.close()
        vote.start_new_seasons()

        self.assertEqual(level_of(reload_group()), level_after(EXP_PER_TRAINING))
        self.assertEqual(FreshStartVote.objects.get(id=self.vote.id).status, FreshStartVote.DONE)

    def test_trainee_in_two_votes_closing_together_starts_over_once(self):
        other_group = self.create_group(trainees=[self.arnold], group_id=OTHER_GROUP_ID)
        other_vote = FreshStartVote.objects.create(group=other_group.pk, executes_at=SEASON_START)
        other_vote.add_participant(self.arnold)

        self.assertEqual([trainee.id for trainee in self.run_vote(self.arnold)], ['1'])
        other_vote.close()
        self.assertEqual(other_vote.start_new_seasons(), [])
        self.assertEqual(reload_trainee('1').season_number, 2)

        self.assertEqual(FreshStartVote.objects.get(id=other_vote.id).undo(), [])
        self.assertEqual(reload_trainee('1').season_number, 2)
        self.assertEqual([trainee.id for trainee in FreshStartVote.objects.get(id=self.vote.id).undo()], ['1'])
        self.assertEqual(reload_trainee('1').season_number, 1)


class TelegramTestCase(DatabaseTestCase):
    """Drives handlers with real telegram Updates and a bot that accepts only the real Bot API."""

    def setUp(self):
        super(TelegramTestCase, self).setUp()
        self.bot = mock.create_autospec(Bot, instance=True)
        self.updater = Updater(token=FAKE_TOKEN)
        self.bot.defaults = None
        self.updater.dispatcher.bot = self.bot  # The bot that jobs and the dispatcher pass on.
        self.logger = logging.getLogger('test')

    def make_context(self, args=None):
        context = mock.Mock(args=args or [])
        context.bot = self.bot
        return context

    def make_update(self, user_id='1', first_name='Arnold', text=None, callback_data=None):
        """A real telegram Update from the group, as sent by the given user."""
        user = {'id': int(user_id), 'first_name': first_name, 'is_bot': False}
        message = {'message_id': 7, 'date': 0, 'chat': {'id': int(GROUP_ID), 'type': 'group'},
                   'from': user, 'text': text}
        if callback_data is None:
            return Update.de_json({'update_id': 1, 'message': message}, self.bot)

        return Update.de_json({'update_id': 1, 'callback_query': {
            'id': '1', 'from': user, 'chat_instance': '1', 'data': callback_data, 'message': message,
        }}, self.bot)

    def sent_messages(self):
        """(chat id, text) of every message the bot sent."""
        return [(str(call.kwargs['chat_id']), call.kwargs['text']) for call in self.bot.send_message.call_args_list]


class TestFreshStartCommand(TelegramTestCase):

    def setUp(self):
        super(TestFreshStartCommand, self).setUp()
        self.command = FreshStartCommand(tasks={}, updater=self.updater, logger=self.logger)

        self.arnold = self.create_trainee('1', 'Arnold')
        self.ronnie = self.create_trainee('2', 'Ronnie')
        for _ in range(3):  # Level 2.
            self.arnold.level.gain_exp(exp=EXP_PER_TRAINING)
        self.arnold.save()
        self.group = self.create_group(trainees=[self.arnold, self.ronnie])
        self.other_group = self.create_group(trainees=[self.arnold], group_id=OTHER_GROUP_ID)
        self.vote = FreshStartVote.objects.create(group=self.group.pk, executes_at=SEASON_START, message_id=7)

    def tap(self, response, user_id='1', first_name='Arnold'):
        """Tap a button of the vote message, returns the popup answer."""
        self.bot.answerCallbackQuery.reset_mock()
        callback_data = '{} {} {}'.format(FreshStartCommand.FRESH_START_QUERY_IDENTIFIER, self.vote.id, response)
        update = self.make_update(user_id=user_id, first_name=first_name, callback_data=callback_data)
        self.command.fresh_start_callback_query(update, self.make_context())
        return self.bot.answerCallbackQuery.call_args.kwargs['text']

    def close_vote(self):
        self.command._close_vote(CloseFreshStartVote(vote_id=str(self.vote.id)), self.make_context())

    def test_closing_is_scheduled_at_local_midnight_and_never_skipped(self):
        self.command._schedule_vote_closing(self.vote)

        job, = self.updater.job_queue.jobs()
        self.assertEqual(job.job.trigger.run_date, TZ.localize(SEASON_START))
        self.assertEqual(job.job.trigger.run_date.utcoffset(), timedelta(hours=3))
        self.assertIsNone(job.job.misfire_grace_time)

    def test_job_only_hands_the_closing_to_the_dispatcher(self):
        """The job runs in parallel to handlers, so it must not touch trainees or groups."""
        self.vote.add_participant(self.arnold)
        context = self.make_context()
        context.job.context = str(self.vote.id)

        self.command._queue_vote_closing(context)

        queued = self.updater.dispatcher.update_queue.get_nowait()
        self.assertIsInstance(queued, CloseFreshStartVote)
        self.assertEqual(queued.vote_id, str(self.vote.id))
        self.assertEqual(FreshStartVote.objects.get(id=self.vote.id).status, FreshStartVote.PENDING)
        self.assertEqual(reload_trainee('1').season_number, 1)

    def test_overdue_vote_closes_once_the_bot_starts(self):
        """The whole path a deploy takes: open vote in the DB, bot starts, the job queue hands
        the closing to the running dispatcher."""
        overdue = datetime(2020, 1, 1)  # The job queue uses the real clock.
        FreshStartVote.objects.filter(id=self.vote.id).update_one(set__executes_at=overdue)
        self.vote.add_participant(self.arnold)

        closing_threads = []
        start_new_seasons = FreshStartVote.start_new_seasons

        def record_thread(vote):
            closing_threads.append(threading.current_thread())
            return start_new_seasons(vote)

        self.command.start()
        dispatcher_thread = threading.Thread(target=self.updater.dispatcher.start)
        with mock.patch.object(FreshStartVote, 'start_new_seasons', record_thread):
            dispatcher_thread.start()
            self.updater.job_queue.start()
            try:
                give_up_at = time.monotonic() + 10
                while (FreshStartVote.objects.get(id=self.vote.id).status != FreshStartVote.DONE
                       and time.monotonic() < give_up_at):
                    time.sleep(0.05)
            finally:
                self.updater.job_queue.stop()
                self.updater.dispatcher.stop()
                dispatcher_thread.join()

        self.assertEqual(closing_threads, [dispatcher_thread])

        arnold = reload_trainee('1')
        self.assertEqual((arnold.season_number, arnold.season_started_at, level_of(arnold)), (2, overdue, (1, 0)))
        self.assertEqual(FreshStartVote.objects.get(id=self.vote.id).status, FreshStartVote.DONE)
        self.assertEqual([chat_id for chat_id, _ in self.sent_messages()], [GROUP_ID, GROUP_ID, OTHER_GROUP_ID])

    def test_command_opens_one_vote_per_group(self):
        self.vote.delete()
        self.bot.send_message.return_value = mock.Mock(message_id=42)

        self.command._handler(self.make_update(text='/fresh_start'), self.make_context())
        vote = FreshStartVote.objects.get_pending(self.group)
        self.assertEqual((vote.message_id, vote.executes_at, vote.created_by), (42, datetime(2026, 10, 22), '1'))
        self.assertEqual(vote.participants, [])
        self.assertIn('22/10', self.sent_messages()[-1][1])
        closing, reminder = self.updater.job_queue.jobs()
        self.assertEqual((closing.callback, closing.context), (self.command._queue_vote_closing, str(vote.id)))
        self.assertEqual(closing.job.trigger.run_date, TZ.localize(datetime(2026, 10, 22)))
        self.assertEqual((reminder.callback, reminder.context), (self.command._queue_vote_reminder, str(vote.id)))
        self.assertEqual(reminder.job.trigger.run_date, TZ.localize(datetime(2026, 10, 21, 22)))
        self.assertIsNone(reminder.job.misfire_grace_time)

        self.command._handler(self.make_update(user_id='2', first_name='Ronnie', text='/fresh_start'),
                              self.make_context())
        self.assertEqual(FreshStartVote.objects.count(), 1)
        self.assertEqual(self.bot.send_message.call_args.kwargs['text'], FreshStartCommand.VOTE_ALREADY_OPEN_MSG)
        self.assertEqual(self.bot.send_message.call_args.kwargs['reply_to_message_id'], 42)
        self.assertEqual(len(self.updater.job_queue.jobs()), 2)

    def test_vote_whose_message_failed_to_send_does_not_block_the_group(self):
        self.vote.delete()
        self.bot.send_message.side_effect = NetworkError('Timed out')

        with self.assertRaises(NetworkError):
            self.command._handler(self.make_update(text='/fresh_start'), self.make_context())
        self.assertIsNone(FreshStartVote.objects.get_pending(self.group))
        failed_vote = FreshStartVote.objects.get()
        self.assertEqual(failed_vote.status, FreshStartVote.CANCELLED)
        self.command._close_vote(CloseFreshStartVote(vote_id=str(failed_vote.id)), self.make_context())
        self.bot.edit_message_reply_markup.assert_not_called()

        self.bot.send_message.side_effect = None
        self.bot.send_message.return_value = mock.Mock(message_id=42)
        self.command._handler(self.make_update(text='/fresh_start'), self.make_context())
        self.assertEqual(FreshStartVote.objects.get_pending(self.group).message_id, 42)

    def make_vote_close_tonight(self):
        FreshStartVote.objects.filter(id=self.vote.id).update_one(set__executes_at=CLOSES_TONIGHT)
        self.vote.reload()

    def remind(self):
        self.command._remind_vote(RemindFreshStartVote(vote_id=str(self.vote.id)), self.make_context())

    def test_buttons_join_and_leave_the_vote(self):
        join, leave = FreshStartCommand.JOIN_RESPONSE, FreshStartCommand.LEAVE_RESPONSE

        self.assertEqual(self.tap(join), FreshStartCommand.JOINED_MSG)
        self.assertIn('Arnold', self.bot.edit_message_text.call_args.kwargs['text'])
        self.assertEqual(self.tap(join), FreshStartCommand.ALREADY_JOINED_MSG)
        self.assertEqual(self.tap(leave, user_id='2', first_name='Ronnie'), FreshStartCommand.NOT_JOINED_MSG)
        self.assertEqual(self.tap(leave), FreshStartCommand.LEFT_MSG)
        self.assertNotIn('Arnold', self.bot.edit_message_text.call_args.kwargs['text'])
        self.assertEqual(self.bot.edit_message_text.call_count, 2)
        self.assertEqual(FreshStartVote.objects.get(id=self.vote.id).participants, [])

        self.vote.cancel()
        self.assertEqual(self.tap(join), FreshStartCommand.VOTE_CLOSED_MSG)
        self.assertEqual(FreshStartVote.objects.get(id=self.vote.id).participants, [])

    def test_joining_and_leaving_tell_the_group(self):
        join, leave = FreshStartCommand.JOIN_RESPONSE, FreshStartCommand.LEAVE_RESPONSE

        self.tap(join)
        self.tap(join, user_id='2', first_name='Ronnie')
        self.tap(join)  # Already in.
        self.tap(leave, user_id='2', first_name='Ronnie')
        self.tap(leave)
        self.tap(leave)  # Already out.
        self.vote.cancel()
        self.tap(join)  # Closed.

        self.assertEqual(self.sent_messages(), [
            (GROUP_ID, FreshStartCommand.JOINED_NOTIFICATION_MSG.format(trainee='Arnold', participants='Arnold')),
            (GROUP_ID, FreshStartCommand.JOINED_NOTIFICATION_MSG.format(trainee='Ronnie', participants='Arnold, Ronnie')),
            (GROUP_ID, FreshStartCommand.LEFT_NOTIFICATION_MSG.format(trainee='Ronnie', participants='Arnold')),
            (GROUP_ID, FreshStartCommand.LEFT_NOTIFICATION_MSG.format(trainee='Arnold',
                                                                      participants=FreshStartCommand.NO_PARTICIPANTS_YET)),
        ])
        for call in self.bot.send_message.call_args_list:  # Quoting the vote message.
            self.assertEqual((call.kwargs['reply_to_message_id'], call.kwargs['allow_sending_without_reply']), (7, True))

    def test_joining_tells_the_group_even_when_the_vote_message_fails_to_update(self):
        self.bot.edit_message_text.side_effect = RetryAfter(30)

        with self.assertLogs(self.logger, level='ERROR'):
            self.assertEqual(self.tap(FreshStartCommand.JOIN_RESPONSE), FreshStartCommand.JOINED_MSG)

        self.assertEqual(FreshStartVote.objects.get(id=self.vote.id).participants, ['1'])
        self.assertEqual(self.sent_messages(), [
            (GROUP_ID, FreshStartCommand.JOINED_NOTIFICATION_MSG.format(trainee='Arnold', participants='Arnold')),
        ])

    def test_joining_tells_the_group_even_when_the_tap_fails_to_be_answered(self):
        for error in (TimedOut(), BadRequest('Query is too old and response timeout expired or query id is invalid')):
            self.bot.reset_mock()
            self.bot.answerCallbackQuery.side_effect = error

            with self.assertLogs(self.logger, level='ERROR'):
                self.tap(FreshStartCommand.JOIN_RESPONSE)
            self.assertEqual(FreshStartVote.objects.get(id=self.vote.id).participants, ['1'])
            self.assertIn('Arnold', self.bot.edit_message_text.call_args.kwargs['text'])
            self.assertEqual(self.sent_messages(), [
                (GROUP_ID, FreshStartCommand.JOINED_NOTIFICATION_MSG.format(trainee='Arnold', participants='Arnold')),
            ])

            with self.assertLogs(self.logger, level='ERROR'):
                self.tap(FreshStartCommand.LEAVE_RESPONSE)

    def test_joining_still_counts_when_telling_the_group_fails(self):
        self.bot.send_message.side_effect = RetryAfter(30)

        with self.assertLogs(self.logger, level='ERROR'):
            self.assertEqual(self.tap(FreshStartCommand.JOIN_RESPONSE), FreshStartCommand.JOINED_MSG)

        self.assertEqual(FreshStartVote.objects.get(id=self.vote.id).participants, ['1'])
        self.assertIn('Arnold', self.bot.edit_message_text.call_args.kwargs['text'])

    def test_job_only_hands_the_reminder_to_the_dispatcher(self):
        self.make_vote_close_tonight()
        context = self.make_context()
        context.job.context = str(self.vote.id)

        self.command._queue_vote_reminder(context)

        queued = self.updater.dispatcher.update_queue.get_nowait()
        self.assertIsInstance(queued, RemindFreshStartVote)
        self.assertEqual(queued.vote_id, str(self.vote.id))
        self.bot.send_message.assert_not_called()
        self.assertFalse(FreshStartVote.objects.get(id=self.vote.id).reminded)

    def test_reminder_quotes_the_vote_and_lists_who_is_in(self):
        self.make_vote_close_tonight()
        self.vote.add_participant(self.arnold)
        self.vote.add_participant(self.ronnie)

        self.remind()
        self.remind()  # E.g. after a restart, or a second instance of the bot.

        self.bot.send_message.assert_called_once_with(
            chat_id=GROUP_ID,
            text=FreshStartCommand.REMINDER_MSG.format(participants='Arnold, Ronnie'),
            reply_to_message_id=7,
            allow_sending_without_reply=True,
        )
        self.assertTrue(FreshStartVote.objects.get(id=self.vote.id).reminded)
        self.assertEqual(FreshStartVote.objects.get(id=self.vote.id).status, FreshStartVote.PENDING)
        self.assertEqual(reload_trainee('1').season_number, 1)

    def test_reminder_when_nobody_is_in_yet(self):
        self.make_vote_close_tonight()

        self.remind()

        self.assertEqual(self.sent_messages(), [
            (GROUP_ID, FreshStartCommand.REMINDER_MSG.format(participants=FreshStartCommand.NO_PARTICIPANTS_YET)),
        ])

    def test_no_reminder_once_the_vote_is_due_or_not_open(self):
        self.make_vote_close_tonight()
        self.vote.add_participant(self.arnold)
        with mock.patch('{}.NOW'.format(__name__), CLOSES_TONIGHT):
            self.remind()  # Still open, but due: it is about to close.
        self.assertFalse(FreshStartVote.objects.get(id=self.vote.id).reminded)

        for status in (FreshStartVote.CLOSING, FreshStartVote.DONE, FreshStartVote.CANCELLED, FreshStartVote.UNDONE):
            FreshStartVote.objects.filter(id=self.vote.id).update_one(set__status=status)
            self.remind()

        self.bot.send_message.assert_not_called()

    def test_reminder_after_the_closing_is_not_sent(self):
        """With the bot down at the deadline, the closing and the reminder can both be queued.

        The clock is left before the deadline, so only the closing keeps the reminder from
        being sent.

        """
        self.make_vote_close_tonight()
        self.vote.add_participant(self.arnold)
        self.close_vote()
        self.bot.reset_mock()

        self.remind()

        self.bot.send_message.assert_not_called()
        self.assertEqual(self.updater.job_queue.jobs(), ())

    def test_failed_reminder_is_retried(self):
        self.make_vote_close_tonight()

        with mock.patch.object(FreshStartVote, 'mark_reminded', side_effect=RuntimeError('DB unreachable')):
            with self.assertLogs(self.logger, level='ERROR'):
                self.remind()
        self.bot.send_message.assert_not_called()
        retry, = self.updater.job_queue.jobs()
        self.assertEqual((retry.callback, retry.context), (self.command._queue_vote_reminder, str(self.vote.id)))
        self.assertAlmostEqual(retry.job.trigger.run_date.timestamp(),
                               time.time() + FreshStartCommand.RETRY_DELAY.total_seconds(), delta=60)
        self.assertIsNone(retry.job.misfire_grace_time)

        self.remind()  # The retry.
        self.assertEqual(self.bot.send_message.call_count, 1)

    def test_reminder_that_fails_to_load_who_is_in_is_not_lost(self):
        self.make_vote_close_tonight()
        self.vote.add_participant(self.arnold)

        with mock.patch.object(FreshStartCommand, '_get_participants_names',
                               side_effect=ServerSelectionTimeoutError('No servers found')):
            with self.assertLogs(self.logger, level='ERROR'):
                self.remind()
        self.assertFalse(FreshStartVote.objects.get(id=self.vote.id).reminded)
        retry, = self.updater.job_queue.jobs()
        self.assertEqual(retry.callback, self.command._queue_vote_reminder)

        self.remind()  # The retry.
        self.assertEqual(self.sent_messages(), [
            (GROUP_ID, FreshStartCommand.REMINDER_MSG.format(participants='Arnold')),
        ])

    def test_reminder_telegram_fails_to_send_is_not_sent_twice(self):
        self.make_vote_close_tonight()
        self.bot.send_message.side_effect = Unauthorized('Forbidden: bot was kicked from the group chat')

        with self.assertLogs(self.logger, level='ERROR'):
            self.remind()
        self.remind()

        self.assertEqual(self.bot.send_message.call_count, 1)
        self.assertEqual(self.updater.job_queue.jobs(), ())

    def test_reminder_is_sent_from_the_dispatcher(self):
        """The whole path: the reminder is scheduled, its job hands it to the running dispatcher."""
        # The job queue uses the real clock, so with a vote that closed in 2020 the reminder
        # runs right away, and the frozen clock is set to before that vote closed.
        vote_closes_at = datetime(2020, 1, 2)
        FreshStartVote.objects.filter(id=self.vote.id).update_one(set__executes_at=vote_closes_at)
        self.vote.reload()
        reminding_threads = []
        mark_reminded = FreshStartVote.mark_reminded

        def record_thread(vote):
            reminding_threads.append(threading.current_thread())
            return mark_reminded(vote)

        dispatcher_thread = threading.Thread(target=self.updater.dispatcher.start)
        with mock.patch('{}.NOW'.format(__name__), datetime(2020, 1, 1, 23)), \
                mock.patch.object(FreshStartVote, 'mark_reminded', record_thread):
            self.command._schedule_vote_reminder(self.vote)
            dispatcher_thread.start()
            self.updater.job_queue.start()
            try:
                give_up_at = time.monotonic() + 10
                while not self.bot.send_message.called and time.monotonic() < give_up_at:
                    time.sleep(0.05)
            finally:
                self.updater.job_queue.stop()
                self.updater.dispatcher.stop()
                dispatcher_thread.join()

        self.assertEqual(reminding_threads, [dispatcher_thread])
        self.assertEqual(self.sent_messages(), [
            (GROUP_ID, FreshStartCommand.REMINDER_MSG.format(participants=FreshStartCommand.NO_PARTICIPANTS_YET)),
        ])

    def test_closing_starts_the_new_seasons_and_tells_every_group(self):
        self.vote.add_participant(self.arnold)
        self.close_vote()

        arnold = reload_trainee('1')
        self.assertEqual((arnold.season_number, level_of(arnold)), (2, (1, 0)))
        self.assertEqual(reload_trainee('2').season_number, 1)
        self.assertEqual(level_of(reload_group()), (1, 0))
        self.bot.edit_message_reply_markup.assert_called_once_with(chat_id=GROUP_ID, message_id=7, reply_markup=None)

        (ranking_chat, ranking), (new_season_chat, new_season), (other_chat, other) = self.sent_messages()
        self.assertEqual((ranking_chat, new_season_chat, other_chat), (GROUP_ID, GROUP_ID, OTHER_GROUP_ID))
        self.assertIn('1. Arnold <Level 2', ranking)  # The ranking from before the reset.
        self.assertIn('Arnold', new_season)
        self.assertNotIn('Ronnie', new_season)
        self.assertEqual(other, FreshStartCommand.NEW_SEASON_MSG_TO_OTHER_GROUPS.format(trainees='Arnold'))

    def test_failed_closing_is_retried_and_blocks_another_vote_until_then(self):
        self.vote.add_participant(self.arnold)

        with mock.patch.object(FreshStartVote, 'start_new_seasons', side_effect=RuntimeError('DB unreachable')):
            with self.assertLogs(self.logger, level='ERROR'):
                self.close_vote()
        self.assertEqual(FreshStartVote.objects.get(id=self.vote.id).status, FreshStartVote.CLOSING)
        retry, = self.updater.job_queue.jobs()
        self.assertEqual((retry.callback, retry.context), (self.command._queue_vote_closing, str(self.vote.id)))
        self.assertAlmostEqual(retry.job.trigger.run_date.timestamp(),
                               time.time() + FreshStartCommand.RETRY_DELAY.total_seconds(), delta=60)

        self.command._handler(self.make_update(user_id='2', first_name='Ronnie', text='/fresh_start'),
                              self.make_context())
        self.assertEqual(self.sent_messages()[-1][1], FreshStartCommand.VOTE_ALREADY_OPEN_MSG)
        self.assertEqual(FreshStartVote.objects.count(), 1)

        self.close_vote()  # The retry.
        self.assertEqual(FreshStartVote.objects.get(id=self.vote.id).status, FreshStartVote.DONE)
        self.assertEqual(reload_trainee('1').season_number, 2)

    def test_vote_message_is_updated_only_after_the_reset(self):
        """Telegram can take seconds, which must not delay the reset past midnight."""
        self.vote.add_participant(self.arnold)
        seasons_when_telegram_was_called = []
        self.bot.edit_message_reply_markup.side_effect = (
            lambda **kwargs: seasons_when_telegram_was_called.append(reload_trainee('1').season_number))
        self.bot.send_message.side_effect = (
            lambda **kwargs: seasons_when_telegram_was_called.append(reload_trainee('1').season_number))

        self.close_vote()

        self.assertEqual(seasons_when_telegram_was_called, [2, 2, 2, 2])

    def test_unfinished_votes_are_scheduled_when_the_bot_starts(self):
        closing_vote = FreshStartVote.objects.create(group=self.other_group.pk, executes_at=SEASON_START,
                                                     participants=['1'], status=FreshStartVote.CLOSING)
        FreshStartVote.objects.create(group=self.group.pk, executes_at=SEASON_START, status=FreshStartVote.DONE)
        open_vote = FreshStartVote.objects.create(group='-300', executes_at=CLOSES_TONIGHT)
        # Saved before reminders existed.
        FreshStartVote._get_collection().update_one({'_id': open_vote.id}, {'$unset': {'reminded': ''}})
        reminded_vote = FreshStartVote.objects.create(group='-400', executes_at=CLOSES_TONIGHT, reminded=True)

        self.command.start()

        jobs = self.updater.job_queue.jobs()
        self.assertEqual(sorted(job.context for job in jobs if job.callback == self.command._queue_vote_closing),
                         sorted([str(self.vote.id), str(closing_vote.id), str(open_vote.id), str(reminded_vote.id)]))
        # self.vote is overdue, it closes as soon as the bot starts, without a reminder.
        reminder, = [job for job in jobs if job.callback == self.command._queue_vote_reminder]
        self.assertEqual(reminder.context, str(open_vote.id))
        self.assertEqual(reminder.job.trigger.run_date, TZ.localize(datetime(2026, 10, 20, 22)))

    def test_votes_are_scheduled_once_the_db_is_back_when_it_is_down_as_the_bot_starts(self):
        self.make_vote_close_tonight()

        with mock.patch.object(FreshStartVote.FreshStartVoteQuerySet, 'get_unfinished',
                               side_effect=ServerSelectionTimeoutError('No servers found')):
            with self.assertLogs(self.logger, level='ERROR'):
                self.command.start()
        retry, = self.updater.job_queue.jobs()
        self.assertEqual(retry.callback, self.command._schedule_unfinished_votes)
        self.assertAlmostEqual(retry.job.trigger.run_date.timestamp(),
                               time.time() + FreshStartCommand.RETRY_DELAY.total_seconds(), delta=60)
        self.assertIsNone(retry.job.misfire_grace_time)

        self.updater.job_queue.scheduler.remove_all_jobs()
        self.command._schedule_unfinished_votes(self.make_context())  # The retry.
        self.assertEqual(sorted(job.callback.__name__ for job in self.updater.job_queue.jobs()),
                         ['_queue_vote_closing', '_queue_vote_reminder'])

    def test_reminder_is_at_22_local_time_across_daylight_saving_changes(self):
        for now, closes_at, utc_offset in ((datetime(2026, 10, 20), datetime(2026, 10, 26), 2),  # After the 25/10 change.
                                           (datetime(2027, 3, 20), datetime(2027, 3, 27), 3)):  # After the 26/3 change.
            self.updater.job_queue.scheduler.remove_all_jobs()
            FreshStartVote.objects.filter(id=self.vote.id).update_one(set__executes_at=closes_at)
            self.vote.reload()

            with mock.patch('{}.NOW'.format(__name__), now):
                self.command._schedule_vote_reminder(self.vote)

            reminder, = self.updater.job_queue.jobs()
            self.assertEqual(reminder.job.trigger.run_date.replace(tzinfo=None), closes_at - timedelta(hours=2))
            self.assertEqual(reminder.job.trigger.run_date.utcoffset(), timedelta(hours=utc_offset))

    def test_no_reminder_is_scheduled_for_a_vote_that_is_not_open(self):
        self.make_vote_close_tonight()
        for status in (FreshStartVote.CLOSING, FreshStartVote.DONE, FreshStartVote.CANCELLED, FreshStartVote.UNDONE):
            FreshStartVote.objects.filter(id=self.vote.id).update_one(set__status=status)
            self.vote.reload()
            self.command._schedule_vote_reminder(self.vote)

        self.assertEqual(self.updater.job_queue.jobs(), ())

    def test_reminder_the_bot_was_down_for_is_scheduled_until_the_vote_closes(self):
        self.make_vote_close_tonight()

        with mock.patch('{}.NOW'.format(__name__), datetime(2026, 10, 20, 23, 59)):
            self.command.start()
        reminder, = [job for job in self.updater.job_queue.jobs() if job.callback == self.command._queue_vote_reminder]
        self.assertEqual(reminder.job.trigger.run_date, TZ.localize(datetime(2026, 10, 20, 22)))  # Runs right away.

        self.updater.job_queue.scheduler.remove_all_jobs()
        with mock.patch('{}.NOW'.format(__name__), CLOSES_TONIGHT):
            self.command.start()
        self.assertEqual([job.callback for job in self.updater.job_queue.jobs()], [self.command._queue_vote_closing])

    def test_training_after_the_reset_counts_in_the_new_season(self):
        self.vote.add_participant(self.arnold)
        self.close_vote()
        trained = TrainedCommand(tasks={}, updater=self.updater, logger=self.logger)

        trained._handler(self.make_update(text='/trained'), self.make_context())

        arnold = reload_trainee('1')
        self.assertEqual(level_of(arnold), level_after(EXP_PER_TRAINING))
        self.assertEqual(arnold.get_training_statistics()[0], 1)
        self.assertEqual(level_of(arnold.past_seasons[0]), level_after(3 * EXP_PER_TRAINING))
        self.assertEqual(level_of(reload_group()), level_after(EXP_PER_TRAINING))
        self.assertEqual(level_of(reload_group(OTHER_GROUP_ID)), level_after(EXP_PER_TRAINING))

    def test_closing_twice_starts_one_season(self):
        self.vote.add_participant(self.arnold)
        self.close_vote()
        self.bot.reset_mock()
        self.close_vote()

        self.assertEqual(reload_trainee('1').season_number, 2)
        self.bot.send_message.assert_not_called()

    def test_closing_with_nobody_in_resets_nothing(self):
        self.close_vote()

        self.assertEqual(level_of(reload_trainee('1')), level_after(3 * EXP_PER_TRAINING))
        self.assertEqual(reload_trainee('1').season_number, 1)
        self.assertEqual(self.sent_messages(), [(GROUP_ID, FreshStartCommand.NOBODY_JOINED_MSG)])

    def test_closing_still_resets_when_telegram_fails(self):
        self.vote.add_participant(self.arnold)
        self.bot.send_message.side_effect = Unauthorized('Forbidden: bot was kicked from the group chat')
        self.bot.edit_message_reply_markup.side_effect = Unauthorized('Forbidden: bot was kicked from the group chat')

        with self.assertLogs(self.logger, level='ERROR') as logs:
            self.close_vote()

        self.assertEqual(reload_trainee('1').season_number, 2)
        self.assertEqual(self.bot.send_message.call_count, 3)
        self.assertEqual(len(logs.records), 4)  # The keyboard and the three messages.


class TestAdminFreshStart(TelegramTestCase):

    def setUp(self):
        super(TestAdminFreshStart, self).setUp()
        self.command = AdminCommand(tasks={}, updater=self.updater, logger=self.logger)
        Admin.objects.create(id='1')
        self.arnold = self.create_trainee('1', 'Arnold')
        self.train(self.arnold, 13)
        self.group = self.create_group(trainees=[self.arnold])
        self.vote = FreshStartVote.objects.create(group=self.group.pk, executes_at=SEASON_START)

    def admin(self, *args):
        self.command._handler(self.make_update(text='/admin ' + ' '.join(args)), self.make_context(args=list(args)))
        return self.sent_messages()[-1][1]

    def test_cancel_closes_the_open_vote(self):
        FreshStartVote.objects.filter(id=self.vote.id).update_one(set__message_id=7)

        self.assertEqual(self.admin('--cancel-fresh-start'), AdminCommand.SUCCEEDED_TO_RUN_COMMAND_MSG)
        self.assertEqual(FreshStartVote.objects.get(id=self.vote.id).status, FreshStartVote.CANCELLED)
        self.bot.edit_message_reply_markup.assert_called_once_with(chat_id=GROUP_ID, message_id=7, reply_markup=None)
        self.assertEqual(self.admin('--cancel-fresh-start'), AdminCommand.NO_OPEN_FRESH_START_VOTE_MSG)

    def test_undo_restores_the_last_fresh_start(self):
        self.assertEqual(self.admin('--undo-fresh-start'), AdminCommand.NO_FRESH_START_TO_UNDO_MSG)

        self.vote.add_participant(self.arnold)
        self.vote.close()
        self.vote.start_new_seasons()
        self.assertEqual(reload_trainee('1').season_number, 2)

        self.assertEqual(self.admin('--undo-fresh-start'),
                         AdminCommand.UNDID_FRESH_START_MSG.format(executes_at='15/10/26 00:00', trainees='Arnold'))
        self.assertEqual(level_of(reload_trainee('1')), level_after(EXP_PER_TRAINING))
        self.assertEqual(self.admin('--undo-fresh-start'), AdminCommand.NO_FRESH_START_TO_UNDO_MSG)

    def test_non_admins_cannot_undo(self):
        self.vote.add_participant(self.arnold)
        self.vote.close()
        self.vote.start_new_seasons()

        update = self.make_update(user_id='2', first_name='Ronnie', text='/admin --undo-fresh-start')
        self.command._handler(update, self.make_context(args=['--undo-fresh-start']))

        self.assertEqual(self.sent_messages()[-1][1], AdminCommand.NOT_ADMIN_MSG)
        self.assertEqual(reload_trainee('1').season_number, 2)


class TestMyStatistics(TelegramTestCase):

    def setUp(self):
        super(TestMyStatistics, self).setUp()
        self.command = MyStatisticsCommand(tasks={}, updater=self.updater, logger=self.logger)
        self.arnold = self.create_trainee('1', 'Arnold')
        self.create_group(trainees=[self.arnold])
        self.train(self.arnold, 13)
        self.train(self.arnold, 14)

    def my_statistics(self):
        self.command._handler(self.make_update(text='/my_statistics'), self.make_context())
        return self.sent_messages()[-1][1]

    def test_without_seasons_the_message_is_unchanged(self):
        msg = self.my_statistics()

        self.assertNotIn(MyStatisticsCommand.PAST_SEASONS_MSG, msg)
        self.assertEqual(msg, MyStatisticsCommand.TRAINEE_STATISTICS_MSG.format(
            trained_days=2, missed_training_days=0, percentage=100,
            num_of_training_days_per_week='2.00', level=reload_trainee().level))

    def test_shows_the_current_season_and_the_past_ones(self):
        reload_trainee().start_new_season(started_at=SEASON_START)
        self.train(reload_trainee(), 15)

        msg = self.my_statistics()

        self.assertTrue(msg.startswith('עונה 2 (מאז 15/10/2026)\n'))
        self.assertIn('מספר הימים שהתאמנת בהם: 1\n', msg)
        self.assertTrue(msg.endswith('עונות קודמות:\nעונה 1: <Level 2 (0/7)>, 2 ימי אימון'))


if __name__ == '__main__':
    unittest.main()
