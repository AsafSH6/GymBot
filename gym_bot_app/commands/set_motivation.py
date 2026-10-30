import hashlib
import unicodedata
from datetime import datetime

from mongoengine import NotUniqueError
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, MessageEntity, Update
from telegram.error import TelegramError
from telegram.ext import CallbackContext, CallbackQueryHandler, Filters

from gym_bot_app import MUSCLE_EMOJI, WEIGHT_LIFTER_EMOJI
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


def sentence_fingerprint(text):
    """Short fingerprint of the sentence, telling it apart from the ones the trainee sets after it.

    The callback data of a button is limited to 64 bytes, too short for the sentence itself.

    """
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:8]


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

    The sentence is set in the group the command was sent in. A trainee who is in other
    groups too is asked whether to use it in all of them, which replaces their sentence there.

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

    SCOPE_QUERY_IDENTIFIER = 'motivation_scope'
    ALL_GROUPS_SCOPE = 'all'
    THIS_GROUP_SCOPE = 'this'
    SCOPE_QUESTION_MSG = 'להשתמש בו גם בשאר הקבוצות שלך? זה יחליף את המשפט שלך שם'
    ALL_GROUPS_BUTTON_TEXT = 'בכל הקבוצות'
    THIS_GROUP_BUTTON_TEXT = 'רק בקבוצה הזאת'
    SET_IN_ALL_GROUPS_MSG = 'המשפט שלך עכשיו בכל הקבוצות שלך ' + MUSCLE_EMOJI
    KEPT_IN_THIS_GROUP_MSG = 'בסדר, בשאר הקבוצות לא שיניתי כלום'
    NOT_YOUR_SENTENCE_MSG = 'זה לא המשפט שלך יא בוט'
    SENTENCE_ALREADY_REPLACED_MSG = 'המשפט הזה כבר הוחלף'

    def __init__(self, *args, **kwargs):
        super(SetMotivationCommand, self).__init__(*args, **kwargs)
        self.updater.dispatcher.add_handler(
            CallbackQueryHandler(pattern='{identifier} '.format(identifier=self.SCOPE_QUERY_IDENTIFIER),
                                 callback=self.scope_callback_query)
        )

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

        old_quote = self._store_quote(trainee=trainee, group=group, text=text)

        if old_quote is None:
            msg = self.ADDED_MOTIVATION_MSG
        else:
            msg = self.REPLACED_MOTIVATION_MSG.format(old_text=old_quote.text, new_text=text)

        reply_markup = None
        if self._get_other_groups(trainee=trainee, group_id=group.id):
            msg += '\n\n' + self.SCOPE_QUESTION_MSG
            reply_markup = self._get_scope_keyboard(trainee=trainee, text=text)

        update.message.reply_text(quote=True, text=msg, reply_markup=reply_markup, disable_web_page_preview=True)

    def scope_callback_query(self, update: Update, context: CallbackContext):
        """Response handler of the question whether to use the sentence in all the groups of the trainee.

        Only the trainee who set the sentence can answer, and only while it is still their
        sentence in the group. Using it in all groups replaces their sentence in each of them.

        Anyone in the group can tap the buttons, so the tap is checked before anything else.
        Unlike the decorators, it neither loads the group nor adds whoever tapped to its trainees.

        """
        query = update.callback_query
        _, owner_id, scope, fingerprint = query.data.split()
        group_id = str(query.message.chat_id)
        self.logger.info('Motivation scope callback query of trainee %s in group %s answered %s by %s',
                         owner_id, group_id, scope, update.effective_user.id)

        if str(update.effective_user.id) != owner_id:
            self._answer(query, text=self.NOT_YOUR_SENTENCE_MSG)
            return

        quote = PersonalMotivationQuote.objects(group=group_id, trainee=owner_id).first()
        if quote is None or sentence_fingerprint(quote.text) != fingerprint:
            outcome_msg = self.SENTENCE_ALREADY_REPLACED_MSG
        elif scope == self.ALL_GROUPS_SCOPE:
            trainee = quote.trainee.fetch()
            for other_group in self._get_other_groups(trainee=trainee, group_id=group_id):
                self._store_quote(trainee=trainee, group=other_group, text=quote.text)
            outcome_msg = self.SET_IN_ALL_GROUPS_MSG
        else:
            outcome_msg = self.KEPT_IN_THIS_GROUP_MSG

        # The sentences are already stored, so failing to answer the tap or to update the
        # message is only logged. E.g. a tap made while the bot was down is too old to answer.
        self._answer(query, text=outcome_msg)
        try:
            query.edit_message_text(text=self._replace_question(query.message.text, outcome_msg),
                                    reply_markup=None,
                                    disable_web_page_preview=True)
        except TelegramError:
            self.logger.exception('Failed to update the motivation scope message of trainee %s', owner_id)

    def _answer(self, query, text):
        """Answer the tap on a button, logging a failure instead of raising it."""
        try:
            query.answer(text=text)
        except TelegramError:
            self.logger.exception('Failed to answer the motivation scope callback query')

    def _replace_question(self, msg, outcome_msg):
        """The message with the scope question, the question replaced with its outcome."""
        if msg and msg.endswith(self.SCOPE_QUESTION_MSG):
            return msg[:-len(self.SCOPE_QUESTION_MSG)] + outcome_msg

        return outcome_msg

    def _get_scope_keyboard(self, trainee, text):
        callback_data = '{identifier} {trainee_id} {{scope}} {fingerprint}'.format(
            identifier=self.SCOPE_QUERY_IDENTIFIER,
            trainee_id=trainee.id,
            fingerprint=sentence_fingerprint(text)
        )

        return InlineKeyboardMarkup([[
            InlineKeyboardButton(self.ALL_GROUPS_BUTTON_TEXT, callback_data=callback_data.format(scope=self.ALL_GROUPS_SCOPE)),
            InlineKeyboardButton(self.THIS_GROUP_BUTTON_TEXT, callback_data=callback_data.format(scope=self.THIS_GROUP_SCOPE)),
        ]])

    @staticmethod
    def _get_other_groups(trainee, group_id):
        """The groups of the trainee other than the given one, with only their id.

        Loading a whole group loads each of its trainees too, one by one.

        """
        return trainee.groups.filter(id__ne=group_id).only('id')

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

    @classmethod
    def _store_quote(cls, trainee, group, text):
        """Set the trainee's motivation quote in the group.

        Returns:
            PersonalMotivationQuote. the replaced quote, None if the trainee did not have one.

        """
        try:
            return cls._set_quote(trainee=trainee, group=group, text=text)
        except NotUniqueError:  # Lost a race with another insert of this trainee's sentence, now replace it.
            return cls._set_quote(trainee=trainee, group=group, text=text)

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
