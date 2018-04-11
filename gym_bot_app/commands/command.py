# encoding: utf-8
from __future__ import unicode_literals

from telegram.ext import CommandHandler


class Command(object):
    """Telegram gym bot abstract command class.

    DEFAULT_COMMAND_NAME(str): default name of the command that will be used in telegram chat in order to execute this command.

    updater(telegram.ext.Updater): bots' Updater instance.
    logger(logging.logger): logger to write to.

    """
    DEFAULT_COMMAND_NAME = NotImplemented

    def __init__(self, updater, logger):
        self.updater = updater
        self.logger = logger

    def _handler(self, bot, update, *args, **kwargs):
        """Handler of the command.

        Args:
            bot(telegrem.Bot): instance of the bot- received by telegram.
            bot(telegrem.Update): instance of the update- received by telegram.

        """
        raise NotImplementedError('Not implemented command handler method.')

    def start(self, command_name=None, *args, **kwargs):
        """Start handling the incoming requests of the command.

        Args:
            command_name(str): name of the command that will be used in telegram chat in orer to execute this command.
                                if not specified, the default command name will be used.
            args(tuple): will be passed to the dispatcher handler.
            kwargs(dict): will be passed to the dispatcher handler.

        """
        command_name = command_name or self.DEFAULT_COMMAND_NAME
        self.updater.dispatcher.add_handler(CommandHandler(command=command_name,
                                                           callback=self._handler,
                                                           *args, **kwargs))
        self.logger.info('command: %s ', self.__class__.__name__)

