# encoding: utf-8
from __future__ import unicode_literals

from telegram.ext import CommandHandler


class Command(object):
    NAME = NotImplemented

    def __init__(self, dispatcher, updater, logger):
        self.dispatcher = dispatcher
        self.updater = updater
        self.logger = logger

    def _handler(self, bot, update, *args, **kwargs):
        raise NotImplementedError('Not implemented command handler method.')

    def start(self, name=None, *args, **kwargs):
        command_name = name or self.NAME
        self.dispatcher.add_handler(CommandHandler(command=command_name,
                                                   callback=self._handler,
                                                   *args, **kwargs))
        self.logger.info('command: %s ', self.__class__.__name__)

