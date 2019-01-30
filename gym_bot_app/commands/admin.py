# encoding: utf-8
from __future__ import unicode_literals

import argparse
import datetime as dt

from gym_bot_app.models import Admin, EXPEvent, Group
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

    DATETIME_FORMAT = '%d/%m/%y %H:%M'
    NOT_ADMIN_MSG = 'שתוק'
    SUCCEEDED_TO_RUN_COMMAND_MSG = 'בוצע'
    FAILED_TO_RUN_COMMAND_MSG = 'נכשל'
    SOMETHING_WENT_WRONG_MSG = 'exception'
    NEW_EXP_EVENT_CREATED = '{multiplier}x EXP from {start_datetime} to {end_datetime}'

    TASKS = {
        'go_to_gym': GoToGymTask,
        'went_to_gym': WentToGymTask,
        'new_week_select_days': NewWeekSelectDaysTask
    }

    def __init__(self, *args, **kwargs):
        super(AdminCommand, self).__init__(pass_args=True, *args, **kwargs)
        self.parser = argparse.ArgumentParser()
        self.parser.add_argument('--run-task', dest='task_name')
        self.parser.add_argument('--exp-event', dest='exp_event', nargs='+')

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
            if parsed_args.task_name:
                task = self.TASKS[parsed_args.task_name]
                task(updater=self.updater, logger=self.logger).execute()
                self.logger.debug('Finished to execute %s via admin command', parsed_args.task_name)
                update.message.reply_text(quote=True, text=self.SUCCEEDED_TO_RUN_COMMAND_MSG)
            elif parsed_args.exp_event:
                multiplier, start_date, start_time, end_date, end_time = parsed_args.exp_event
                exp_event = EXPEvent.objects.create(
                    multiplier=float(multiplier),
                    start_time=dt.datetime.strptime('{} {}'.format(start_date, start_time), self.DATETIME_FORMAT),
                    end_time=dt.datetime.strptime('{} {}'.format(end_date, end_time), self.DATETIME_FORMAT)
                )
                for group in Group.objects.all():
                    bot.send_message(chat_id=group.id,
                                     text=self.NEW_EXP_EVENT_CREATED.format(multiplier=exp_event.multiplier,
                                                                            start_datetime=exp_event.start_time.strftime(self.DATETIME_FORMAT),
                                                                            end_datetime=exp_event.end_time.strftime(self.DATETIME_FORMAT)))
        except (AttributeError, KeyError, SystemExit) as e:  # argparse raises SystemExit if something went wrong.
            self.logger.error('Failed to execute task via admin due to wrong usage with args %s, exception %s', args, e)
            update.message.reply_text(quote=True, text=self.FAILED_TO_RUN_COMMAND_MSG)
        except Exception as e:
            self.logger.error('Failed to execute task via admin with args %s, exception %s', args, e)
            exception_msg = '{msg} {exc}'.format(msg=self.SOMETHING_WENT_WRONG_MSG, exc=e)
            update.message.reply_text(quote=True, text=exception_msg)
