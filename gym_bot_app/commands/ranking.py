# encoding: utf-8
from __future__ import unicode_literals

from gym_bot_app.decorators import get_group
from gym_bot_app.commands import Command


class RankingCommand(Command):
    """Telegram gym bot ranking command.

    Sends group ranking based on trainees level.

    """
    DEFAULT_COMMAND_NAME = 'ranking'
    GROUP_RANKING_MESSAGE = 'Top {limit} trainees'
    TRAINEES_LIMIT = 5


    def __init__(self, *args, **kwargs):
        super(RankingCommand, self).__init__(*args, **kwargs)

    @get_group
    def _handler(self, bot, update, group):
        """Override method to handle ranking command.

        Takes top trainees based on their level and exp.

        """
        self.logger.info('Ranking statistics command in %s', group)

        ranking = sorted(group.trainees,
                         key=lambda trainee: (trainee.level.number, trainee.level.exp),
                         reverse=True)[:self.TRAINEES_LIMIT]
        self.logger.debug('Group ranking is %s', ranking)

        msg = '\n'.join('{idx}. {name} {level}'.format(idx=(idx + 1), name=trainee.first_name, level=trainee.level)
                        for idx, trainee in enumerate(ranking))
        update.message.reply_text(quote=True,
                                  text=msg)
