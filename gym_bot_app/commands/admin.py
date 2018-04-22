# encoding: utf-8
from __future__ import unicode_literals

import argparse

from gym_bot_app.models import Admin
from gym_bot_app.commands import Command
from gym_bot_app.tasks import (GoToGymTask,
                               WentToGymTask,
                               NewWeekSelectDaysTask)


class AdminCommand(Command):
    """Telegram gym bot admin command.

    Allows to execute admin commands.

    Options:
        --run-task task_name: run the given task right now.

    """
    DEFAULT_COMMAND_NAME = 'admin'

    NOT_ADMIN_MSG = 'שתוק'
    SUCCEEDED_TO_RUN_COMMAND_MSG = 'בוצע'
    FAILED_TO_RUN_COMMAND_MSG = 'נכשל'
    SOMETHING_WENT_WRONG_MSG = 'exception'

    TASKS = {
        'go_to_gym': GoToGymTask,
        'went_to_gym': WentToGymTask,
        'new_week_select_days': NewWeekSelectDaysTask
    }

    def __init__(self, *args, **kwargs):
        super(AdminCommand, self).__init__(*args, **kwargs)
        self.parser = argparse.ArgumentParser()
        self.parser.add_argument('--run-task', dest='task_name')

    def _handler(self, bot, update, args):
        """Override method to handle admin command.

        Execute admin commands.

        """
        self.logger.info('Admin command from %s with args %s', update.effective_user.id, args)

        if not Admin.objects.is_admin(update.effective_user.id):  # not an admin
            self.logger.debug('User is not an admin')
            update.message.reply_text(quote=True, text=self.NOT_ADMIN_MSG)
            return

        try:
            parsed_args = self.parser.parse_args(args)
            task = self.TASKS[parsed_args.task_name]
            task(updater=self.updater, logger=self.logger).execute()
            self.logger.debug('Finished to execute %s via admin command', parsed_args.task_name)
            update.message.reply_text(quote=True, text=self.SUCCEEDED_TO_RUN_COMMAND_MSG)
        except (AttributeError, KeyError, SystemExit) as e:
            self.logger.error('Failed to execute task via admin due to wrong usage with args %s, exception %s', args, e)
            update.message.reply_text(quote=True, text=self.FAILED_TO_RUN_COMMAND_MSG)
        except Exception as e:
            self.logger.error('Failed to execute task via admin with args %s, exception %s', args, e)
            exception_msg = '{msg} {exc}'.format(msg=self.SOMETHING_WENT_WRONG_MSG, exc=e)
            update.message.reply_text(quote=True, text=exception_msg)

    def start(self, *args, **kwargs):
        """Override method to update kwargs in order to request to pass args in command handler."""
        kwargs['pass_args'] = True
        return super(AdminCommand, self).start(*args, **kwargs)

