"""Tests for running a task in every group.

They run against mongomock, an in-memory MongoDB, or TEST_MONGODB_URL if set (see
tests.connect_test_db). The Telegram errors are built from the descriptions the Bot API
sends, so they go through the same parsing as in production.
"""
import logging
import unittest

from telegram.error import BadRequest, NetworkError, TimedOut, Unauthorized

from gym_bot_app.decorators import run_for_all_groups
from gym_bot_app.models import Group
from tests import connect_test_db, disconnect_test_db

setUpModule = connect_test_db
tearDownModule = disconnect_test_db

GROUP_IDS = ('-100', '-200', '-300')


def run_in_all_groups(errors):
    """Run a task in every group, raising the given error in its group.

    Args:
        errors(dict): error to raise, by group id.

    Returns:
        list. ids of the groups the task ran in, in order.

    """
    ran_in = []

    @run_for_all_groups
    def task(group):
        ran_in.append(group.id)
        if group.id in errors:
            raise errors[group.id]

    task()
    return ran_in


def deleted_groups():
    return sorted(group.id for group in Group.objects(is_deleted=True))


class TestRunForAllGroups(unittest.TestCase):

    def setUp(self):
        Group.objects.delete()
        for group_id in GROUP_IDS:
            Group.objects.create(id=group_id)

    def test_runs_in_every_group_that_is_not_deleted(self):
        Group.objects.get(id='-200').delete()

        self.assertCountEqual(run_in_all_groups({}), ['-100', '-300'])

    def test_group_whose_chat_is_not_found_is_deleted(self):
        """E.g. a deleted group, which Telegram answers with 400 "Bad Request: chat not found"."""
        with self.assertLogs(__name__, level=logging.INFO) as logs:
            ran_in = run_in_all_groups({'-200': BadRequest('Bad Request: chat not found')})

        self.assertCountEqual(ran_in, GROUP_IDS)
        self.assertEqual(deleted_groups(), ['-200'])
        self.assertEqual([record.levelno for record in logs.records], [logging.INFO])

    def test_group_that_removed_or_blocked_the_bot_is_deleted(self):
        run_in_all_groups({'-200': Unauthorized('Forbidden: bot was kicked from the group chat')})

        self.assertEqual(deleted_groups(), ['-200'])

    def test_other_errors_keep_the_group_and_log_the_error_itself(self):
        errors = {'-100': BadRequest('Bad Request: message is too long'),
                  '-200': NetworkError('Bad Gateway'),
                  '-300': KeyError('trainee')}

        with self.assertLogs(__name__, level=logging.ERROR) as logs:
            ran_in = run_in_all_groups(errors)

        self.assertCountEqual(ran_in, GROUP_IDS)
        self.assertEqual(deleted_groups(), [])
        self.assertEqual([record.exc_info[1] for record in logs.records], [errors[group_id] for group_id in ran_in])

    def test_timeout_keeps_the_group(self):
        with self.assertLogs(__name__, level=logging.ERROR):
            run_in_all_groups({'-200': TimedOut()})

        self.assertEqual(deleted_groups(), [])


if __name__ == '__main__':
    unittest.main()
