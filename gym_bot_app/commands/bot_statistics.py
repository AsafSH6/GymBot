# encoding: utf-8
from __future__ import unicode_literals

from gym_bot_app.decorators import get_group
from gym_bot_app.commands import Command
import textwrap


class BotStatisticsCommand(Command):
    """Telegram gym bot bot statistics command.

    Sends bot statistics to the group when requested by one of trainees.

    """
    DEFAULT_COMMAND_NAME = 'bot_statistics'
    BOT_STATISTICS_MSG = textwrap.dedent('''
        {level}
        ''')

    def __init__(self, *args, **kwargs):
        super(BotStatisticsCommand, self).__init__(*args, **kwargs)

    @get_group
    def _handler(self, bot, update, group):
        """Override method to handle bot statistics command.

        Checks level of bot in the group and sends it back to the chat.

        """
        self.logger.info('Bot statistics command in %s', group)

        update.message.reply_text(quote=True,
                                  text=self.BOT_STATISTICS_MSG.format(level=group.level))
