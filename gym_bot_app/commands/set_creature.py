# encoding: utf-8
from __future__ import unicode_literals

from gym_bot_app.commands import Command
from gym_bot_app.decorators import get_trainee_and_group


class SetCreatureCommand(Command):
    """Telegram gym bot set creature command.

    Allows trainees choose which creature they wants to be.
    Effects the complement sent after training.

    """
    DEFAULT_COMMAND_NAME = 'set_creature'
    DID_NOT_PROVIDE_CREATURE_MSG = 'לא בחרת איזה יצור אתה רוצה להיות יא בוט'
    SUCCEEDED_TO_SET_CREATURE_MSG = 'מעכשיו אתה {creature} ובוט 3>'

    def __init__(self, *args, **kwargs):
        super(SetCreatureCommand, self).__init__(pass_args=True, *args, **kwargs)

    @get_trainee_and_group
    def _handler(self, bot, update, trainee, group, args):
        """Override method to handle set creature command.

        Sets the given creature in the trainee's personal configurations.

        """
        self.logger.info('Set creature command with %s in %s', trainee, group)

        creature = ' '.join(args)
        if len(creature) is 0:
            self.logger.debug('Trainee did not provide creature')
            update.message.reply_text(quote=True, text=self.DID_NOT_PROVIDE_CREATURE_MSG)
            return

        trainee.personal_configurations.creature = creature
        trainee.save()

        msg = self.SUCCEEDED_TO_SET_CREATURE_MSG.format(creature=creature)
        update.message.reply_text(quote=True, text=msg)

