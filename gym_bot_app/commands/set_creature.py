from telegram import Update
from telegram.ext import CallbackContext

from gym_bot_app import KISSING_HEART_EMOJI
from gym_bot_app.commands import Command
from gym_bot_app.decorators import get_trainee_and_group
from gym_bot_app.models import Trainee, Group


class SetCreatureCommand(Command):
    """Telegram gym bot set creature command.

    Allows trainees choose which creature they wants to be.
    Effects the complement sent after training.

    """
    DEFAULT_COMMAND_NAME = 'set_creature'
    DID_NOT_PROVIDE_CREATURE_MSG = 'לא בחרת איזה יצור אתה רוצה להיות יא בוט\n /set_creature שור עולם'
    SUCCEEDED_TO_SET_CREATURE_MSG = 'מעכשיו אתה {{creature}} ובוט {emoji}'.format(emoji=KISSING_HEART_EMOJI)

    def __init__(self, *args, **kwargs):
        super(SetCreatureCommand, self).__init__(pass_args=True, *args, **kwargs)

    @get_trainee_and_group
    def _handler(self, update: Update, context: CallbackContext, trainee: Trainee, group: Group):
        """Override method to handle set creature command.

        Sets the given creature in the trainee's personal configurations.

        """
        self.logger.info('Set creature command with %s in %s', trainee, group)

        creature = ' '.join(context.args)
        if len(creature) == 0:
            self.logger.debug('Trainee did not provide creature')
            update.message.reply_text(quote=True, text=self.DID_NOT_PROVIDE_CREATURE_MSG)
            return

        trainee.personal_configurations.creature = creature
        trainee.save()

        msg = self.SUCCEEDED_TO_SET_CREATURE_MSG.format(creature=creature)
        update.message.reply_text(quote=True, text=msg)

