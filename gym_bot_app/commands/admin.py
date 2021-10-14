import argparse
import datetime as dt

from telegram import Update
from telegram.error import Unauthorized
from telegram.ext import CallbackContext

from gym_bot_app.decorators import get_group
from gym_bot_app.models import Admin, EXPEvent, Group, Trainee
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
    DELETED_GROUP_MSG = 'deleted group successfully'
    FAILED_TO_NOTIFY_GROUP_EXP_EVENT = 'Failed to notify {group} about exp event due to exception: {exc}'

    TASKS = {
        'go_to_gym': GoToGymTask,
        'went_to_gym': WentToGymTask,
        'new_week_select_days': NewWeekSelectDaysTask
    }

    def __init__(self, *args, **kwargs):
        super(AdminCommand, self).__init__(pass_args=True, *args, **kwargs)
        self.parser = argparse.ArgumentParser()
        self.parser.add_argument('--run-task', dest='task_name')
        self.parser.add_argument('--delete-group', dest='delete_group', action='store_true')
        self.parser.add_argument('--exp-event', dest='exp_event', nargs='+')

    @get_group
    def _handler(self, update: Update, context: CallbackContext, group: Group):
        """Override method to handle admin command.

        Execute admin commands.

        """
        admin_id = update.effective_user.id
        self.logger.info('Admin command from %s with args %s', admin_id, context.args)

        if not Admin.objects.is_admin(admin_id):  # Not an admin
            self.logger.debug('User is not an admin')
            update.message.reply_text(quote=True, text=self.NOT_ADMIN_MSG)
            return

        try:
            parsed_args = self.parser.parse_args(context.args)
            if parsed_args.task_name:
                task = self.TASKS[parsed_args.task_name]
                task(updater=self.updater, logger=self.logger).execute()
                self.logger.debug('Finished to execute %s via admin command', parsed_args.task_name)
                update.message.reply_text(quote=True, text=self.SUCCEEDED_TO_RUN_COMMAND_MSG)
            elif parsed_args.delete_group:
                group.delete()
                self.logger.debug('Finished to delete group %s', group)
                update.message.reply_text(quote=True, text=self.DELETED_GROUP_MSG)
            elif parsed_args.exp_event:
                multiplier, start_date, start_time, end_date, end_time = parsed_args.exp_event
                exp_event = EXPEvent.objects.create(
                    multiplier=float(multiplier),
                    start_time=dt.datetime.strptime('{} {}'.format(start_date, start_time), self.DATETIME_FORMAT),
                    end_time=dt.datetime.strptime('{} {}'.format(end_date, end_time), self.DATETIME_FORMAT)
                )
                new_exp_event_msg = self.NEW_EXP_EVENT_CREATED.format(
                    multiplier=exp_event.multiplier,
                    start_datetime=exp_event.start_time.strftime(self.DATETIME_FORMAT),
                    end_datetime=exp_event.end_time.strftime(self.DATETIME_FORMAT)
                )
                for group in Group.objects.filter(is_deleted=False):
                    try:
                        context.bot.send_message(
                            chat_id=group.id,
                            text=new_exp_event_msg
                        )
                    except Unauthorized:
                        group.delete()
                        self.logger.info('Unauthorized group %s - deleted', group)
                    except Exception as e:
                        msg = self.FAILED_TO_NOTIFY_GROUP_EXP_EVENT.format(group=group, exc=e)
                        self.logger.error(msg)
                        context.bot.send_message(
                            chat_id=admin_id,
                            text=msg
                        )
            else:
                context.bot.send_message(
                    chat_id=admin_id,
                    text='Unknown admin command.'
                )
        except (AttributeError, KeyError, SystemExit) as e:  # argparse raises SystemExit if something went wrong.
            self.logger.exception(
                'Failed to execute task via admin due to wrong usage with args: %s',
                context.args
            )
            context.bot.send_message(
                chat_id=admin_id,
                text=self.FAILED_TO_RUN_COMMAND_MSG
            )
        except Exception as e:
            self.logger.exception('Failed to execute task via admin with args %s', context.args)
            exception_msg = self.SOMETHING_WENT_WRONG_MSG.format(exc=e)
            context.bot.send_message(
                chat_id=admin_id,
                text=exception_msg
            )
