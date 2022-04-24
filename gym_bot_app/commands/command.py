from typing import Dict, Type
import logging

from telegram import Update
from telegram.ext import CommandHandler, CallbackContext, Updater

from gym_bot_app.tasks import Task


class Command(object):
    """Telegram gym bot abstract command class.

    DEFAULT_COMMAND_NAME(str): default name of the command that will be used in telegram chat in order to execute this command.

    """
    DEFAULT_COMMAND_NAME = NotImplemented

    # TODO: convert tasks to to TypedDict
    # https://adamj.eu/tech/2021/05/10/python-type-hints-how-to-use-typeddict/
    def __init__(self, tasks: Dict[Type[Task], Task], updater: Updater, logger: logging.Logger, pass_args: bool = False):
        self.tasks = tasks
        self.updater = updater
        self.logger = logger
        self.pass_args = pass_args

    def _handler(self, update: Update, context: CallbackContext, *args, **kwargs):
        """Handler of the command.

        Args:
            bot(telegrem.Bot): instance of the bot- received by telegram.
            bot(telegrem.Update): instance of the update- received by telegram.

        """
        raise NotImplementedError('Not implemented command handler method.')

    def start(self, command_name=None, *args, **kwargs):
        """Start handling the incoming requests of the command.

        Args:
            command_name(str): name of the command that will be used in telegram chat in order to execute this command.
                                if not specified, the default command name will be used.
            args(tuple): will be passed to the dispatcher handler.
            kwargs(dict): will be passed to the dispatcher handler.

        """
        command_name = command_name or self.DEFAULT_COMMAND_NAME
        self.updater.dispatcher.add_handler(CommandHandler(command=command_name,
                                                           callback=self._handler,
                                                           pass_args=self.pass_args,
                                                           *args, **kwargs))
        self.logger.info("Set %s with command name '%s'", self.__class__.__name__, command_name)

