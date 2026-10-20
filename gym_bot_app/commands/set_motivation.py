import unicodedata
from datetime import datetime

from mongoengine import NotUniqueError
from telegram import MessageEntity, Update
from telegram.ext import CallbackContext, Filters

from gym_bot_app import WEIGHT_LIFTER_EMOJI
from gym_bot_app.commands import Command
from gym_bot_app.decorators import get_trainee_and_group
from gym_bot_app.models import MAX_PERSONAL_MOTIVATION_LENGTH, PersonalMotivationQuote, Trainee, Group


MAX_MOTIVATION_LINES = 3
MAX_COMBINING_MARKS_IN_A_ROW = 4  # Hebrew vowel points put up to 3 marks on a letter.

# Explicit direction embeddings, overrides and isolates. They keep going past the end of the
# sentence and flip the author name after it. The direction marks Hebrew text uses (LRM, RLM)
# are not among them.
BIDI_CONTROL_CHARACTERS = frozenset('‪‫‬‭‮⁦⁧⁨⁩')

# Telegram turns these into live links, link previews and notifications in the bot's own message.
LINK_AND_TAG_ENTITY_TYPES = frozenset((MessageEntity.URL,
                                       MessageEntity.TEXT_LINK,
                                       MessageEntity.EMAIL,
                                       MessageEntity.MENTION,
                                       MessageEntity.TEXT_MENTION,
                                       MessageEntity.BOT_COMMAND))


def is_visible(text):
    """Check whether the text has anything to see, a letter, number, punctuation or symbol."""
    return any(unicodedata.category(char)[0] in 'LNPS' for char in text)


def has_forbidden_characters(text):
    """Check whether the text has characters that break how the quote is shown.

    Those are control characters other than a new line, invalid characters (lone surrogates),
    explicit direction controls, and long runs of combining marks, which pile up into a smear
    over the messages around it.

    """
    combining_marks_in_a_row = 0
    for char in text:
        category = unicodedata.category(char)
        if (category == 'Cc' and char != '\n') or category == 'Cs' or char in BIDI_CONTROL_CHARACTERS:
            return True

        combining_marks_in_a_row = combining_marks_in_a_row + 1 if category in ('Mn', 'Me') else 0
        if combining_marks_in_a_row > MAX_COMBINING_MARKS_IN_A_ROW:
            return True

    return False


def has_links_or_tags(message):
    """Check whether the message has links, emails, mentions or commands after the command itself.

    Uses the entities Telegram found in the message, as Telegram finds the same ones again
    in the bot's message.

    """
    return any(entity.type in LINK_AND_TAG_ENTITY_TYPES and entity.offset > 0 for entity in message.entities)


class SetMotivationCommand(Command):
    """Telegram gym bot set motivation command.

    Allows trainees add their own motivation sentence to the motivation quotes of the group.
    Each trainee has one sentence in each group, setting another one replaces it.

    The sentence is stored and sent exactly as Telegram delivered it, as plain text. Sentences
    that would show differently than written, ping someone or post a link are rejected.

    """
    DEFAULT_COMMAND_NAME = 'set_motivation'
    DID_NOT_PROVIDE_MOTIVATION_MSG = 'לא כתבת משפט יא בוט\n/set_motivation תמיד יש עוד חזרה אחת'
    CURRENT_MOTIVATION_MSG = 'המשפט שלך בקבוצה הזאת:\n"{text}"\nכדי להחליף: /set_motivation משפט חדש'
    MOTIVATION_TOO_LONG_MSG = 'ארוך מדי יא בוט, עד {max_length} תווים'.format(max_length=MAX_PERSONAL_MOTIVATION_LENGTH)
    TOO_MANY_LINES_MSG = 'יותר מדי שורות יא בוט, עד {max_lines}'.format(max_lines=MAX_MOTIVATION_LINES)
    FORBIDDEN_CHARACTERS_MSG = 'יש במשפט תווים מוזרים יא בוט, תכתוב רגיל'
    LINKS_AND_TAGS_MSG = 'בלי קישורים, תיוגים ופקודות יא בוט'
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

        if not is_visible(text):
            self.logger.debug('Trainee did not provide motivation')
            current_quote = PersonalMotivationQuote.objects(group=group.pk, trainee=trainee.pk).first()
            if current_quote is None:
                msg = self.DID_NOT_PROVIDE_MOTIVATION_MSG
            else:
                msg = self.CURRENT_MOTIVATION_MSG.format(text=current_quote.text)

            update.message.reply_text(quote=True, text=msg, disable_web_page_preview=True)
            return

        problem_msg = self._find_problem(message=update.message, text=text)
        if problem_msg is not None:
            # The sentence itself is not logged, it is free text from the trainee.
            self.logger.info('Rejected motivation of %s in %s: %s', trainee, group, problem_msg)
            update.message.reply_text(quote=True, text=problem_msg)
            return

        try:
            old_quote = self._set_quote(trainee=trainee, group=group, text=text)
        except NotUniqueError:  # Lost a race with another insert of this trainee's sentence, now replace it.
            old_quote = self._set_quote(trainee=trainee, group=group, text=text)

        if old_quote is None:
            msg = self.ADDED_MOTIVATION_MSG
        else:
            msg = self.REPLACED_MOTIVATION_MSG.format(old_text=old_quote.text, new_text=text)

        update.message.reply_text(quote=True, text=msg, disable_web_page_preview=True)

    def _find_problem(self, message, text):
        """Find why the sentence can't be used.

        Args:
            message(telegram.Message): the command message.
            text(str): the sentence, the message text after the command.

        Returns:
            str. message explaining the problem to the trainee, None if the sentence is fine.

        """
        if len(text) > MAX_PERSONAL_MOTIVATION_LENGTH:
            return self.MOTIVATION_TOO_LONG_MSG

        if text.count('\n') >= MAX_MOTIVATION_LINES:
            return self.TOO_MANY_LINES_MSG

        if has_forbidden_characters(text):
            return self.FORBIDDEN_CHARACTERS_MSG

        if has_links_or_tags(message):
            return self.LINKS_AND_TAGS_MSG

        return None

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
