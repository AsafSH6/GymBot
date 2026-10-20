from datetime import datetime

from mongoengine import NotUniqueError
from telegram import Update
from telegram.ext import CallbackContext, Filters

from gym_bot_app import WEIGHT_LIFTER_EMOJI
from gym_bot_app.commands import Command
from gym_bot_app.decorators import get_trainee_and_group
from gym_bot_app.models import MAX_PERSONAL_MOTIVATION_LENGTH, PersonalMotivationQuote, Trainee, Group


class SetMotivationCommand(Command):
    """Telegram gym bot set motivation command.

    Allows trainees add their own motivation sentence to the motivation quotes of the group.
    Each trainee has one sentence in each group, setting another one replaces it.

    """
    DEFAULT_COMMAND_NAME = 'set_motivation'
    DID_NOT_PROVIDE_MOTIVATION_MSG = 'לא כתבת משפט יא בוט\n/set_motivation תמיד יש עוד חזרה אחת'
    CURRENT_MOTIVATION_MSG = 'המשפט שלך בקבוצה הזאת:\n"{text}"\nכדי להחליף: /set_motivation משפט חדש'
    MOTIVATION_TOO_LONG_MSG = 'ארוך מדי יא בוט, עד {max_length} תווים'.format(max_length=MAX_PERSONAL_MOTIVATION_LENGTH)
    ADDED_MOTIVATION_MSG = 'המשפט שלך נוסף למוטיבציות של הקבוצה {emoji}'.format(emoji=WEIGHT_LIFTER_EMOJI)
    REPLACED_MOTIVATION_MSG = 'החלפתי את המשפט שלך:\n"{old_text}"\nב:\n"{new_text}"'

    def start(self, command_name=None, *args, **kwargs):
        """Override method to ignore edited messages.

        Telegram sends the command again when its message is edited, and an edit has no
        update.message, which the decorators use. To change the sentence the trainee sends it again.

        """
        kwargs.setdefault('filters', ~Filters.update.edited_message)
        super(SetMotivationCommand, self).start(command_name, *args, **kwargs)

    @get_trainee_and_group
    def _handler(self, update: Update, context: CallbackContext, trainee: Trainee, group: Group):
        """Override method to handle set motivation command.

        Sets the given sentence as the trainee's motivation quote in the group, or shows the
        current one if no sentence was given.

        """
        self.logger.info('Set motivation command with %s in %s', trainee, group)

        # The raw text keeps the sentence as written, context.args would collapse its whitespace.
        command_and_text = update.message.text.split(maxsplit=1)
        text = command_and_text[1].strip() if len(command_and_text) > 1 else ''

        if len(text) == 0:
            self.logger.debug('Trainee did not provide motivation')
            current_quote = PersonalMotivationQuote.objects(group=group.pk, trainee=trainee.pk).first()
            if current_quote is None:
                msg = self.DID_NOT_PROVIDE_MOTIVATION_MSG
            else:
                msg = self.CURRENT_MOTIVATION_MSG.format(text=current_quote.text)

            update.message.reply_text(quote=True, text=msg)
            return

        if len(text) > MAX_PERSONAL_MOTIVATION_LENGTH:
            self.logger.debug('Trainee provided too long motivation')
            update.message.reply_text(quote=True, text=self.MOTIVATION_TOO_LONG_MSG)
            return

        try:
            old_quote = self._set_quote(trainee=trainee, group=group, text=text)
        except NotUniqueError:  # Lost a race with another insert of this trainee's sentence, now replace it.
            old_quote = self._set_quote(trainee=trainee, group=group, text=text)

        if old_quote is None:
            msg = self.ADDED_MOTIVATION_MSG
        else:
            msg = self.REPLACED_MOTIVATION_MSG.format(old_text=old_quote.text, new_text=text)

        update.message.reply_text(quote=True, text=msg)

    @staticmethod
    def _set_quote(trainee, group, text):
        """Set the trainee's motivation quote in the group, in a single atomic update.

        Returns:
            PersonalMotivationQuote. the replaced quote, None if the trainee did not have one.

        """
        return PersonalMotivationQuote.objects(group=group.pk, trainee=trainee.pk).modify(
            upsert=True,
            new=False,
            set__text=text,
            set__updated_at=datetime.now()
        )
