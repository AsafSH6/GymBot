"""Tests for personal motivation quotes.

They run against mongomock, an in-memory MongoDB (see requirements-test.txt), so they
never depend on a database. Set TEST_MONGODB_URL to run them against a real MongoDB
instead. Every test wipes that database, so its name must contain "test".

Handlers are driven with real telegram Updates, and the bot is an autospec of the real
telegram.Bot, so a call with a wrong method or argument name fails the test.
"""
import logging
import unittest
from unittest import mock

from mongoengine import NotUniqueError
from telegram import Bot, MessageEntity, Update
from telegram.error import TelegramError
from telegram.ext import CommandHandler, Updater
from telegram.utils.helpers import DEFAULT_NONE

from gym_bot_app.commands import MotivationQuotesCommand, SetMotivationCommand
from gym_bot_app.models import Group, PersonalMotivationQuote, Trainee
from gym_bot_app.quotes import QUOTE_LIST, QUOTE_MSG
from tests import connect_test_db, disconnect_test_db

# Well-formed but fake -- Bot() only validates the token's shape, it never calls out.
FAKE_TOKEN = '123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
BOT_USERNAME = 'GymiousBot'

GROUP_ID = '-100'
OTHER_GROUP_ID = '-200'
THIRD_GROUP_ID = '-300'

MODELS = (Group, PersonalMotivationQuote, Trainee)


setUpModule = connect_test_db
tearDownModule = disconnect_test_db


def stored_quotes():
    """(group id, trainee id, text) of every stored personal motivation quote."""
    return sorted((quote.group.pk, quote.trainee.pk, quote.text) for quote in PersonalMotivationQuote.objects)


class MotivationTestCase(unittest.TestCase):
    """Drives both commands with real telegram Updates and a bot that accepts only the real Bot API.

    Trainees and groups are created by the commands themselves, on their first message, as in production.

    """

    def setUp(self):
        for model in MODELS:
            model.objects.delete()

        self.bot = mock.create_autospec(Bot, instance=True)
        self.bot.defaults = None
        self.bot.username = BOT_USERNAME
        self.updater = Updater(token=FAKE_TOKEN)
        self.updater.dispatcher.bot = self.bot
        logger = logging.getLogger('test')
        self.set_motivation_command = SetMotivationCommand(tasks={}, updater=self.updater, logger=logger)
        self.motivate_me_command = MotivationQuotesCommand(tasks={}, updater=self.updater, logger=logger)

    def make_update(self, text, user_id='1', first_name='Arnold', group_id=GROUP_ID, edited=False, entities=()):
        """A real telegram Update with a command message from the group, as sent by the given user.

        Args:
            entities(iterable): entities Telegram found in the text after the command, as dicts.

        """
        command = text.split(maxsplit=1)[0]
        message = {'message_id': 7, 'date': 0, 'chat': {'id': int(group_id), 'type': 'group'},
                   'from': {'id': int(user_id), 'first_name': first_name, 'is_bot': False},
                   'text': text,
                   'entities': [{'type': 'bot_command', 'offset': 0, 'length': len(command)}, *entities]}
        return Update.de_json({'update_id': 1, 'edited_message' if edited else 'message': message}, self.bot)

    def reply_to(self, handler, text, **kwargs):
        """Send the command message to the handler, returns the text the bot replied with.

        The whole call is kept in self.reply_call.

        """
        self.bot.send_message.reset_mock()
        handler(self.make_update(text, **kwargs), mock.Mock())
        self.reply_call = self.bot.send_message.call_args
        self.assertEqual(str(self.reply_call.kwargs['chat_id']), kwargs.get('group_id', GROUP_ID))
        self.assertEqual(self.reply_call.kwargs['reply_to_message_id'], 7)
        # Sentences are free text from trainees, so they are only ever sent as plain text.
        self.assertIn(self.reply_call.kwargs.get('parse_mode'), (None, DEFAULT_NONE))
        self.assertIsNone(self.reply_call.kwargs.get('entities'))
        return self.reply_call.kwargs['text']

    def set_motivation(self, text, **kwargs):
        return self.reply_to(self.set_motivation_command._handler, text, **kwargs)

    def motivate_me(self, **kwargs):
        """Ask to be motivated, picking the last quote of the pool instead of a random one.

        Returns:
            list. the pool the quote was picked from.
            str. the text the bot replied with.

        """
        with mock.patch('gym_bot_app.commands.motivation_quotes.random.choices',
                        side_effect=lambda pool, weights: [pool[-1]]) as choices:
            reply = self.reply_to(self.motivate_me_command._handler, '/motivate_me', **kwargs)

        pool, = choices.call_args.args
        self.weights = choices.call_args.kwargs['weights']
        return pool, reply


class TestSetMotivation(MotivationTestCase):

    def test_adds_the_sentence(self):
        reply = self.set_motivation('/set_motivation Never skip leg day')

        self.assertEqual(reply, SetMotivationCommand.ADDED_MOTIVATION_MSG)
        self.assertEqual(stored_quotes(), [(GROUP_ID, '1', 'Never skip leg day')])

    def test_setting_again_replaces_the_sentence(self):
        self.set_motivation('/set_motivation Never skip leg day')
        reply = self.set_motivation('/set_motivation Light weight baby')

        self.assertEqual(reply, SetMotivationCommand.REPLACED_MOTIVATION_MSG.format(old_text='Never skip leg day',
                                                                                    new_text='Light weight baby'))
        self.assertEqual(stored_quotes(), [(GROUP_ID, '1', 'Light weight baby')])

    def test_one_sentence_per_trainee_in_each_group(self):
        self.set_motivation('/set_motivation Arnold in the group')
        self.set_motivation('/set_motivation Arnold in the other group', group_id=OTHER_GROUP_ID)
        self.set_motivation('/set_motivation Ronnie in the group', user_id='2', first_name='Ronnie')
        self.set_motivation('/set_motivation Arnold replaced in the group')

        self.assertEqual(stored_quotes(), [(GROUP_ID, '1', 'Arnold replaced in the group'),
                                           (GROUP_ID, '2', 'Ronnie in the group'),
                                           (OTHER_GROUP_ID, '1', 'Arnold in the other group')])

    def test_without_a_sentence_explains_how_to_set_one(self):
        for text in ('/set_motivation', '/set_motivation   ', '/set_motivation@{}'.format(BOT_USERNAME)):
            with self.subTest(text=text):
                self.assertEqual(self.set_motivation(text), SetMotivationCommand.DID_NOT_PROVIDE_MOTIVATION_MSG)

        self.assertEqual(stored_quotes(), [])

    def test_without_a_sentence_shows_the_current_one_of_this_group(self):
        self.set_motivation('/set_motivation Never skip leg day')

        self.assertEqual(self.set_motivation('/set_motivation'),
                         SetMotivationCommand.CURRENT_MOTIVATION_MSG.format(text='Never skip leg day'))
        self.assertEqual(self.set_motivation('/set_motivation', group_id=OTHER_GROUP_ID),
                         SetMotivationCommand.DID_NOT_PROVIDE_MOTIVATION_MSG)
        self.assertEqual(stored_quotes(), [(GROUP_ID, '1', 'Never skip leg day')])

    def test_too_long_sentence_is_rejected_and_keeps_the_current_one(self):
        self.set_motivation('/set_motivation Never skip leg day')

        reply = self.set_motivation('/set_motivation ' + 'א' * 201)

        self.assertEqual(reply, SetMotivationCommand.MOTIVATION_TOO_LONG_MSG)
        self.assertEqual(stored_quotes(), [(GROUP_ID, '1', 'Never skip leg day')])

    def test_longest_allowed_sentence_is_accepted(self):
        self.set_motivation('/set_motivation ' + 'א' * 200)

        self.assertEqual(stored_quotes(), [(GROUP_ID, '1', 'א' * 200)])

    def test_keeps_the_sentence_as_written(self):
        self.set_motivation('/set_motivation@{}   Line one\n  line   two  '.format(BOT_USERNAME))

        self.assertEqual(stored_quotes(), [(GROUP_ID, '1', 'Line one\n  line   two')])

    def test_losing_a_race_to_another_insert_replaces_it(self):
        set_quote = SetMotivationCommand._set_quote

        def racing_set_quote(trainee, group, text):
            if not PersonalMotivationQuote.objects:
                # The same trainee's sentence was inserted between the find and the insert.
                PersonalMotivationQuote(group=group.pk, trainee=trainee.pk, text='The other insert').save()
                raise NotUniqueError()
            return set_quote(trainee=trainee, group=group, text=text)

        with mock.patch.object(SetMotivationCommand, '_set_quote', side_effect=racing_set_quote):
            reply = self.set_motivation('/set_motivation Never skip leg day')

        self.assertEqual(reply, SetMotivationCommand.REPLACED_MOTIVATION_MSG.format(old_text='The other insert',
                                                                                    new_text='Never skip leg day'))
        self.assertEqual(stored_quotes(), [(GROUP_ID, '1', 'Never skip leg day')])

    def test_database_allows_one_sentence_per_trainee_in_a_group(self):
        PersonalMotivationQuote(group=GROUP_ID, trainee='1', text='First').save()
        PersonalMotivationQuote(group=OTHER_GROUP_ID, trainee='1', text='Other group').save()
        PersonalMotivationQuote(group=GROUP_ID, trainee='2', text='Other trainee').save()

        with self.assertRaises(NotUniqueError):
            PersonalMotivationQuote(group=GROUP_ID, trainee='1', text='Second').save()

    def test_edited_command_does_not_reach_the_handler(self):
        """An edit has no update.message, which the decorators need."""
        self.set_motivation_command.start()
        handler, = [handler for handler in self.updater.dispatcher.handlers[0] if isinstance(handler, CommandHandler)]

        self.assertFalse(handler.check_update(self.make_update('/set_motivation Fixed typo', edited=True)))
        self.assertTrue(handler.check_update(self.make_update('/set_motivation Never skip leg day')))
        self.assertTrue(handler.check_update(self.make_update('/set_motivation@{} Never skip leg day'.format(BOT_USERNAME))))


class TestMotivateMe(MotivationTestCase):

    def test_without_personal_sentences_picks_from_the_quotes_list(self):
        pool, reply = self.motivate_me()

        self.assertEqual(pool, QUOTE_LIST)
        self.assertEqual(reply, QUOTE_MSG.format(**QUOTE_LIST[-1]))

    def test_personal_sentence_is_signed_with_the_name_of_who_set_it(self):
        self.set_motivation('/set_motivation Never skip leg day', user_id='2', first_name='Ronnie')

        pool, reply = self.motivate_me()

        self.assertEqual(len(pool), len(QUOTE_LIST) + 1)
        self.assertEqual(reply, '"Never skip leg day", Ronnie')

    def test_pool_has_the_current_sentence_of_every_trainee_of_the_group(self):
        self.set_motivation('/set_motivation Never skip leg day')
        self.set_motivation('/set_motivation Light weight baby')
        self.set_motivation('/set_motivation Yeah buddy', user_id='2', first_name='Ronnie')
        self.set_motivation('/set_motivation Not in this group', user_id='3', group_id=OTHER_GROUP_ID)

        pool, _ = self.motivate_me()

        self.assertEqual(pool[:len(QUOTE_LIST)], QUOTE_LIST)
        self.assertCountEqual([quote.text for quote in pool[len(QUOTE_LIST):]], ['Light weight baby', 'Yeah buddy'])

    def test_personal_sentences_are_more_likely_than_quotes_of_the_list(self):
        self.set_motivation('/set_motivation Never skip leg day')
        self.set_motivation('/set_motivation Yeah buddy', user_id='2', first_name='Ronnie')

        pool, _ = self.motivate_me()

        weight_of = {quote['text'] if isinstance(quote, dict) else quote.text: weight
                     for quote, weight in zip(pool, self.weights)}
        self.assertEqual(len(self.weights), len(pool))
        self.assertEqual({weight_of[quote['text']] for quote in QUOTE_LIST}, {1})
        self.assertEqual(weight_of['Never skip leg day'], MotivationQuotesCommand.PERSONAL_QUOTE_WEIGHT)
        self.assertEqual(weight_of['Yeah buddy'], MotivationQuotesCommand.PERSONAL_QUOTE_WEIGHT)
        self.assertGreater(MotivationQuotesCommand.PERSONAL_QUOTE_WEIGHT, 1)

    def test_sentences_of_another_group_are_not_in_its_pool(self):
        self.set_motivation('/set_motivation Never skip leg day')

        pool, _ = self.motivate_me(group_id=OTHER_GROUP_ID)

        self.assertEqual(pool, QUOTE_LIST)

    def test_replies_with_one_of_the_quotes_at_random(self):
        self.set_motivation('/set_motivation Never skip leg day', user_id='2', first_name='Ronnie')
        possible_replies = {QUOTE_MSG.format(**quote) for quote in QUOTE_LIST} | {'"Never skip leg day", Ronnie'}

        for _ in range(20):
            self.assertIn(self.reply_to(self.motivate_me_command._handler, '/motivate_me'), possible_replies)


class TestMotivationScope(MotivationTestCase):
    """A trainee who is in other groups too is asked whether to use the sentence in all of them."""

    def join(self, group_id, user_id='1', first_name='Arnold'):
        """The trainee sends a command in the group, which adds them to it."""
        self.motivate_me(group_id=group_id, user_id=user_id, first_name=first_name)

    def buttons(self, reply_call=None):
        """The buttons of the given reply, the last reply if not given."""
        reply_markup = (reply_call or self.reply_call).kwargs.get('reply_markup')
        return [button for row in reply_markup.inline_keyboard for button in row] if reply_markup else []

    def make_callback_update(self, callback_data, user_id='1', first_name='Arnold', message_text=None):
        """A real telegram Update with a tap on a button of a bot message in the group, by the given user."""
        message = {'message_id': 8, 'date': 0, 'chat': {'id': int(GROUP_ID), 'type': 'group'},
                   'from': {'id': 999, 'first_name': 'GymBot', 'is_bot': True},
                   'text': message_text}
        callback_query = {'id': '5', 'chat_instance': '1', 'data': callback_data, 'message': message,
                          'from': {'id': int(user_id), 'first_name': first_name, 'is_bot': False}}
        return Update.de_json({'update_id': 2, 'callback_query': callback_query}, self.bot)

    def tap(self, button_text, user_id='1', first_name='Arnold', reply_call=None):
        """Tap the button with the given text on the given reply, the last reply if not given.

        Returns:
            str. the text the tap was answered with.

        """
        reply_call = reply_call or self.reply_call
        button, = [button for button in self.buttons(reply_call) if button.text == button_text]
        update = self.make_callback_update(button.callback_data, user_id=user_id, first_name=first_name,
                                           message_text=reply_call.kwargs['text'])

        self.bot.answer_callback_query.reset_mock()
        self.bot.edit_message_text.reset_mock()
        self.set_motivation_command.scope_callback_query(update, mock.Mock())
        return self.bot.answer_callback_query.call_args.kwargs['text']

    def edited_text(self):
        """The text the message with the buttons was edited to, None if it was not edited."""
        call = self.bot.edit_message_text.call_args
        if call is None:
            return None

        self.assertEqual(call.kwargs['message_id'], 8)
        self.assertIsNone(call.kwargs['reply_markup'])
        self.assertIs(call.kwargs['disable_web_page_preview'], True)
        self.assertIn(call.kwargs.get('parse_mode'), (None, DEFAULT_NONE))
        return call.kwargs['text']

    def test_trainee_in_one_group_is_not_asked(self):
        self.join(OTHER_GROUP_ID, user_id='2', first_name='Ronnie')

        reply = self.set_motivation('/set_motivation Never skip leg day')

        self.assertEqual(reply, SetMotivationCommand.ADDED_MOTIVATION_MSG)
        self.assertEqual(self.buttons(), [])

    def test_trainee_in_other_groups_is_asked_and_the_sentence_is_set_in_this_group(self):
        self.join(OTHER_GROUP_ID)

        reply = self.set_motivation('/set_motivation Never skip leg day')

        self.assertEqual(reply, SetMotivationCommand.ADDED_MOTIVATION_MSG + '\n\n' + SetMotivationCommand.SCOPE_QUESTION_MSG)
        self.assertEqual([button.text for button in self.buttons()],
                         [SetMotivationCommand.ALL_GROUPS_BUTTON_TEXT, SetMotivationCommand.THIS_GROUP_BUTTON_TEXT])
        self.assertEqual(stored_quotes(), [(GROUP_ID, '1', 'Never skip leg day')])

    def test_replacing_the_sentence_asks_too(self):
        self.join(OTHER_GROUP_ID)
        self.set_motivation('/set_motivation Never skip leg day')

        reply = self.set_motivation('/set_motivation Light weight baby')

        self.assertTrue(reply.startswith(SetMotivationCommand.REPLACED_MOTIVATION_MSG.format(
            old_text='Never skip leg day', new_text='Light weight baby')))
        self.assertTrue(reply.endswith(SetMotivationCommand.SCOPE_QUESTION_MSG))
        self.assertEqual(len(self.buttons()), 2)

    def test_all_groups_replaces_the_sentence_in_every_group_of_the_trainee(self):
        self.join(THIRD_GROUP_ID)
        self.set_motivation('/set_motivation Old sentence', group_id=OTHER_GROUP_ID)
        self.set_motivation('/set_motivation Ronnie in the other group', user_id='2', first_name='Ronnie',
                            group_id=OTHER_GROUP_ID)
        self.join('-400', user_id='2', first_name='Ronnie')
        self.set_motivation('/set_motivation Never skip leg day')

        answer = self.tap(SetMotivationCommand.ALL_GROUPS_BUTTON_TEXT)

        self.assertEqual(answer, SetMotivationCommand.SET_IN_ALL_GROUPS_MSG)
        self.assertEqual(stored_quotes(), [(GROUP_ID, '1', 'Never skip leg day'),
                                           (OTHER_GROUP_ID, '1', 'Never skip leg day'),
                                           (OTHER_GROUP_ID, '2', 'Ronnie in the other group'),
                                           (THIRD_GROUP_ID, '1', 'Never skip leg day')])
        self.assertEqual(self.edited_text(),
                         SetMotivationCommand.ADDED_MOTIVATION_MSG + '\n\n' + SetMotivationCommand.SET_IN_ALL_GROUPS_MSG)

    def test_this_group_keeps_the_sentences_of_the_other_groups(self):
        self.set_motivation('/set_motivation Old sentence', group_id=OTHER_GROUP_ID)
        self.set_motivation('/set_motivation Never skip leg day')

        answer = self.tap(SetMotivationCommand.THIS_GROUP_BUTTON_TEXT)

        self.assertEqual(answer, SetMotivationCommand.KEPT_IN_THIS_GROUP_MSG)
        self.assertEqual(stored_quotes(), [(GROUP_ID, '1', 'Never skip leg day'),
                                           (OTHER_GROUP_ID, '1', 'Old sentence')])
        self.assertEqual(self.edited_text(),
                         SetMotivationCommand.ADDED_MOTIVATION_MSG + '\n\n' + SetMotivationCommand.KEPT_IN_THIS_GROUP_MSG)

    def test_only_the_trainee_who_set_it_can_answer(self):
        self.join(OTHER_GROUP_ID)
        self.join(OTHER_GROUP_ID, user_id='2', first_name='Ronnie')
        self.set_motivation('/set_motivation Never skip leg day')

        for button_text in (SetMotivationCommand.ALL_GROUPS_BUTTON_TEXT, SetMotivationCommand.THIS_GROUP_BUTTON_TEXT):
            with self.subTest(button_text=button_text):
                answer = self.tap(button_text, user_id='2', first_name='Ronnie')

                self.assertEqual(answer, SetMotivationCommand.NOT_YOUR_SENTENCE_MSG)
                self.assertIsNone(self.edited_text())
                self.assertEqual(stored_quotes(), [(GROUP_ID, '1', 'Never skip leg day')])

    def test_tapping_someone_elses_buttons_does_not_add_you_to_the_group(self):
        self.join(OTHER_GROUP_ID)
        self.set_motivation('/set_motivation Never skip leg day')

        self.tap(SetMotivationCommand.ALL_GROUPS_BUTTON_TEXT, user_id='2', first_name='Ronnie')

        self.assertIsNone(Trainee.objects.get(id='2'))
        self.assertEqual([trainee.id for trainee in Group.objects.get(id=GROUP_ID).trainees], ['1'])

    def test_answering_about_a_replaced_sentence_changes_nothing(self):
        self.join(OTHER_GROUP_ID)
        self.set_motivation('/set_motivation Never skip leg day')
        old_reply_call = self.reply_call
        self.set_motivation('/set_motivation Light weight baby')

        answer = self.tap(SetMotivationCommand.ALL_GROUPS_BUTTON_TEXT, reply_call=old_reply_call)

        self.assertEqual(answer, SetMotivationCommand.SENTENCE_ALREADY_REPLACED_MSG)
        self.assertEqual(stored_quotes(), [(GROUP_ID, '1', 'Light weight baby')])
        self.assertEqual(self.edited_text(), SetMotivationCommand.ADDED_MOTIVATION_MSG + '\n\n' +
                         SetMotivationCommand.SENTENCE_ALREADY_REPLACED_MSG)

    def test_deleted_groups_are_left_out(self):
        self.join(OTHER_GROUP_ID)
        Group.objects.get(id=OTHER_GROUP_ID).delete()

        self.set_motivation('/set_motivation Never skip leg day')
        self.assertEqual(self.buttons(), [])

        self.join(THIRD_GROUP_ID)
        self.set_motivation('/set_motivation Never skip leg day')
        self.tap(SetMotivationCommand.ALL_GROUPS_BUTTON_TEXT)

        self.assertEqual(stored_quotes(), [(GROUP_ID, '1', 'Never skip leg day'),
                                           (THIRD_GROUP_ID, '1', 'Never skip leg day')])

    def test_failing_to_answer_or_update_the_message_keeps_the_sentences(self):
        self.join(OTHER_GROUP_ID)
        self.set_motivation('/set_motivation Never skip leg day')
        self.bot.answer_callback_query.side_effect = TelegramError('Query is too old')
        self.bot.edit_message_text.side_effect = TelegramError('Message to edit not found')

        with self.assertLogs('test', level=logging.ERROR) as logs:
            self.tap(SetMotivationCommand.ALL_GROUPS_BUTTON_TEXT)

        self.assertEqual(len(logs.records), 2)
        self.assertEqual(stored_quotes(), [(GROUP_ID, '1', 'Never skip leg day'),
                                           (OTHER_GROUP_ID, '1', 'Never skip leg day')])

    def test_buttons_fit_the_telegram_limit_and_reach_the_handler(self):
        """Telegram rejects callback data over 64 bytes, and user ids keep growing."""
        user_id = str(2 ** 52)
        self.join(OTHER_GROUP_ID, user_id=user_id)
        self.set_motivation('/set_motivation ' + 'א' * 200, user_id=user_id)
        handler, = [handler for handler in self.updater.dispatcher.handlers[0]
                    if handler.callback == self.set_motivation_command.scope_callback_query]

        for button in self.buttons():
            with self.subTest(button=button.text):
                self.assertLessEqual(len(button.callback_data.encode('utf-8')), 64)
                self.assertTrue(handler.check_update(self.make_callback_update(button.callback_data, user_id=user_id)))


def entity_of(text, part, entity_type, **extra):
    """Entity of the given type over the part of the text, as Telegram would send it."""
    return {'type': entity_type, 'offset': text.index(part), 'length': len(part), **extra}


class TestAbuse(MotivationTestCase):
    """Sentences are free text from anyone in the group, and are shown again to the whole group."""

    def assert_rejected(self, text, expected_msg, **kwargs):
        with mock.patch.object(SetMotivationCommand, '_set_quote') as set_quote:
            self.assertEqual(self.set_motivation(text, **kwargs), expected_msg)

        set_quote.assert_not_called()

    def test_database_operators_are_stored_as_plain_text(self):
        self.set_motivation('/set_motivation Yeah buddy', user_id='2', first_name='Ronnie')
        payloads = ('{"$gt": ""}',
                    '{"$set": {"text": "hacked"}}',
                    '$where: function() { sleep(5000) }',
                    "'; db.dropDatabase(); //",
                    'text.$.trainee')

        for payload in payloads:
            with self.subTest(payload=payload):
                self.set_motivation('/set_motivation ' + payload)

                self.assertEqual(stored_quotes(), [(GROUP_ID, '1', payload), (GROUP_ID, '2', 'Yeah buddy')])
                pool, _ = self.motivate_me()
                self.assertCountEqual([quote.text for quote in pool[len(QUOTE_LIST):]], [payload, 'Yeah buddy'])

    def test_markup_is_sent_as_plain_text(self):
        text = '*bold* _italic_ `code` <b>html</b> [click](tg://user?id=2) &amp;'

        self.set_motivation('/set_motivation ' + text)

        self.assertEqual(self.set_motivation('/set_motivation'), SetMotivationCommand.CURRENT_MOTIVATION_MSG.format(text=text))
        self.assertEqual(self.motivate_me()[1], QUOTE_MSG.format(text=text, author='Arnold'))

    def test_links_tags_and_commands_are_rejected(self):
        cases = (('https://evil.example/login', MessageEntity.URL, {}),
                 ('evil.example', MessageEntity.URL, {}),
                 ('click here', MessageEntity.TEXT_LINK, {'url': 'https://evil.example'}),
                 ('me@evil.example', MessageEntity.EMAIL, {}),
                 ('@ronnie_lifts', MessageEntity.MENTION, {}),
                 ('Ronnie', MessageEntity.TEXT_MENTION, {'user': {'id': 2, 'first_name': 'Ronnie', 'is_bot': False}}),
                 ('/fresh_start', MessageEntity.BOT_COMMAND, {}))

        for part, entity_type, extra in cases:
            with self.subTest(entity_type=entity_type, part=part):
                text = '/set_motivation Go train {} now'.format(part)
                self.assert_rejected(text, SetMotivationCommand.LINKS_AND_TAGS_MSG,
                                     entities=[entity_of(text, part, entity_type, **extra)])

        self.assertEqual(stored_quotes(), [])

    def test_hashtags_are_allowed(self):
        text = '/set_motivation Never skip #legday'

        self.set_motivation(text, entities=[entity_of(text, '#legday', MessageEntity.HASHTAG)])

        self.assertEqual(stored_quotes(), [(GROUP_ID, '1', 'Never skip #legday')])

    def test_rejected_sentence_keeps_the_current_one(self):
        self.set_motivation('/set_motivation Never skip leg day')
        text = '/set_motivation Free protein at https://evil.example'

        self.assert_rejected(text, SetMotivationCommand.LINKS_AND_TAGS_MSG,
                             entities=[entity_of(text, 'https://evil.example', MessageEntity.URL)])

        self.assertEqual(stored_quotes(), [(GROUP_ID, '1', 'Never skip leg day')])

    def test_replies_with_a_sentence_never_show_link_previews(self):
        self.set_motivation('/set_motivation Never skip leg day')
        self.assertIs(self.reply_call.kwargs['disable_web_page_preview'], True)

        for text in ('/set_motivation Light weight baby', '/set_motivation'):
            with self.subTest(text=text):
                self.set_motivation(text)
                self.assertIs(self.reply_call.kwargs['disable_web_page_preview'], True)

        self.motivate_me()
        self.assertIs(self.reply_call.kwargs['disable_web_page_preview'], True)

    def test_too_many_lines_are_rejected(self):
        for text in ('a\nb\nc\nd', 'a\n\n\nb', 'a' + '\n' * 150 + 'b'):
            with self.subTest(text=text):
                self.assert_rejected('/set_motivation ' + text, SetMotivationCommand.TOO_MANY_LINES_MSG)

        self.set_motivation('/set_motivation Never\nskip\nleg day')
        self.assertEqual(stored_quotes(), [(GROUP_ID, '1', 'Never\nskip\nleg day')])

    def test_direction_overrides_are_rejected(self):
        """An override keeps going past the sentence and would flip the author name."""
        for char in '‪‫‬‭‮⁦⁧⁨⁩':
            with self.subTest(char=hex(ord(char))):
                self.assert_rejected('/set_motivation evil{}text'.format(char),
                                     SetMotivationCommand.FORBIDDEN_CHARACTERS_MSG)

    def test_control_and_invalid_characters_are_rejected(self):
        for text in ('null\x00byte', 'bell\x07', '\x1b[31mred', 'tab\there', 'carriage\rreturn', 'lone\ud800surrogate'):
            with self.subTest(text=text):
                self.assert_rejected('/set_motivation ' + text, SetMotivationCommand.FORBIDDEN_CHARACTERS_MSG)

    def test_combining_mark_floods_are_rejected(self):
        self.assert_rejected('/set_motivation Z' + '̶́҉' * 10, SetMotivationCommand.FORBIDDEN_CHARACTERS_MSG)

    def test_normal_hebrew_and_emoji_are_accepted(self):
        """Vowel points and shin dots, direction marks around English, and emoji joined by zero width joiners."""
        texts = ('שָׁלוֹם עֲלֵיכֶם',
                 'היום ‎Leg day‎ וזהו',
                 'בוא נזיז ברזלים 🏋️‍♂️💪🏽 1️⃣ 🇮🇱 👨‍👩‍👧',
                 'á' + '́' * 3)

        for text in texts:
            with self.subTest(text=text):
                self.set_motivation('/set_motivation ' + text)
                self.assertEqual(stored_quotes(), [(GROUP_ID, '1', text)])

    def test_invisible_sentence_counts_as_no_sentence(self):
        for text in ('​​​', '‏', '‮', '́', '　  '):
            with self.subTest(text=repr(text)):
                self.assert_rejected('/set_motivation ' + text, SetMotivationCommand.DID_NOT_PROVIDE_MOTIVATION_MSG)

    def test_huge_message_is_rejected_before_the_database(self):
        self.assert_rejected('/set_motivation ' + 'א' * 4000, SetMotivationCommand.MOTIVATION_TOO_LONG_MSG)

    def test_flooding_keeps_one_sentence_per_trainee(self):
        for attempt in range(50):
            self.set_motivation('/set_motivation Attempt {}'.format(attempt))

        self.assertEqual(stored_quotes(), [(GROUP_ID, '1', 'Attempt 49')])


if __name__ == '__main__':
    unittest.main()
