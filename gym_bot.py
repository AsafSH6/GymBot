# encoding: utf-8
from __future__ import unicode_literals

import json
import logging
import threading
from datetime import datetime, timedelta


from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, Filters, MessageHandler, ConversationHandler

from models import User, Group, Day
from utils import get_db_session, upper_first_letter, WEIGHT_LIFTER_EMOJI, DAYS_NAME, THUMBS_DOWN_EMOJI, THUMBS_UP_EMOJI


TOKEN = ''

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)


class GymBot(object):
    def __init__(self, updater, dispatcher):
        self.updater = updater
        self.dispatcher = dispatcher
        self.session = get_db_session()
        self.users = self.session.query(User)
        self.groups = self.session.query(Group)
        self.days = self.session.query(Day)

    def _generate_inline_keyboard_for_registration(self, user):
        already_registered_days = user.days

        keyboard = []
        for idx, day in enumerate(self.days.all()):
            day_name = upper_first_letter(day.name)
            if day in already_registered_days:
                day_name += ' ' + WEIGHT_LIFTER_EMOJI
            keyboard.append([InlineKeyboardButton(day_name, callback_data='register {id} {idx}'.format(id=user.id,
                                                                                                       idx=idx))])

        return InlineKeyboardMarkup(keyboard)

    def register_command(self, bot, update):
        print 'register'
        user_id = update.effective_user.id
        group_id = update.message.chat_id

        user = self.users.get(user_id)
        group = self.groups.get(group_id)

        if user is None:  # new user.
            user = User(id=user_id, first_name=update.effective_user.first_name)
            self.session.add(user)

            if not group:
                group = Group(id=group_id)
                self.session.add(group)
            group.users.append(user)
            print 'created new user and added him to group'

        elif user not in group.users: # user exists but new in the current group.
            print 'User was not in the group.'
            group.users.append(user)

        keyboard = self._generate_inline_keyboard_for_registration(user)
        update.message.reply_text('באיזה ימים אתה מתאמן יא בוט?', reply_markup=keyboard)

    def select_day(self, bot, update):
        print 'select day'
        query = update.callback_query

        user = self.users.get(update.effective_user.id)
        _, user_id, selected_day_index = query.data.split()

        if user is None or user.id != int(user_id):
            bot.answerCallbackQuery(text='אי אפשר לבחור לאחרים יא בוט',
                                    callback_query_id=update.callback_query.id,
                                    parse_mode=ParseMode.HTML)
            return

        selected_day = DAYS_NAME[int(selected_day_index)]
        selected_day = self.days.get(selected_day)
        if user not in selected_day.users:
            selected_day.users.append(user)
        else:
            selected_day.users.remove(user)
        self.session.commit()

        updated_keyboard = self._generate_inline_keyboard_for_registration(user)
        bot.edit_message_reply_markup(chat_id=query.message.chat_id,
                                      message_id=query.message.message_id,
                                      reply_markup=updated_keyboard)

        bot.answerCallbackQuery(text="selected {}".format(upper_first_letter(selected_day.name)),
                                callback_query_id=update.callback_query.id)

    def my_days_command(self, bot, update):
        print 'my days'
        user = self.users.get(update.effective_user.id)
        text = ' '.join(unicode(day) for day in user.days)
        bot.send_message(chat_id=update.message.chat_id,
                         text=text)

    def _groups_daily_timer(self, callback):
        print 'group daily timer'
        for group in self.groups.all():
            print 'checking group', group, 'with users', group.users
            today_name = datetime.now().strftime('%A').lower()
            today = self.days.get(today_name)

            # TODO: use sql query.
            relevant_users = [user for user in today.users if user in group.users]

            callback(group, relevant_users)

    def go_to_gym(self, group, relevant_users):
        print 'go to gym'
        if not relevant_users:
            return
        go_to_gym_plural = 'לכו היום לחדר כושר יא בוטים {training}'
        go_to_gym_individual = 'לך היום לחדר כושר יא בוט {training}'

        training_today_msg = ' '.join('@' + user.first_name for user in relevant_users)

        if len(relevant_users) > 1:
            text = go_to_gym_plural.format(training=training_today_msg)
        else:
            text = go_to_gym_individual.format(training=training_today_msg)

        self.updater.bot.send_message(chat_id=group.id, text=text)

    def went_to_gym(self, group, relevant_users):
        if not relevant_users:
            return
        went_to_gym_plural = 'הלכתם היום לחדכ יא בוטים? {training}'
        went_to_gym_individual = 'הלכת היום לחדכ יא בוט? {training}'

        training_today_msg = ' '.join('@' + user.first_name for user in relevant_users)

        if len(relevant_users) > 1:
            text = went_to_gym_plural.format(training=training_today_msg)
        else:
            text = went_to_gym_individual.format(training=training_today_msg)

        allowed_users = ','.join(unicode(user.id) for user in relevant_users)
        keyboard = [[InlineKeyboardButton('כן',
                         callback_data='went_to_gym [{allowed_users}] yes'.format(allowed_users=allowed_users)),
                    InlineKeyboardButton('אני אפס',
                         callback_data='went_to_gym [{allowed_users}] no'.format(allowed_users=allowed_users))]]

        self.updater.bot.send_message(chat_id=group.id,
                                      text=text,
                                      reply_markup=InlineKeyboardMarkup(keyboard))

    def went_to_gym_answer(self, bot, update):
        print 'went to gym answer'
        query = update.callback_query
        _, allowed_users, answer = query.data.split()
        allowed_users = [int(user_id) for user_id in json.loads(allowed_users)]
        print allowed_users
        user = self.users.get(update.effective_user.id)

        if not user or user.id not in allowed_users:
            bot.answerCallbackQuery(text='זה לא היום שלך להתאמן יא בוט',
                                    callback_query_id=update.callback_query.id)
            return
        if answer == 'yes':
            bot.send_message(chat_id=query.message.chat_id,
                             text='כל הכבוד {user} אלוף!'.format(user=user.first_name))
            bot.answerCallbackQuery(text=THUMBS_UP_EMOJI,
                                    callback_query_id=update.callback_query.id)
        else:
            bot.send_message(chat_id=query.message.chat_id,
                             text='אפס מאופס {user}'.format(user=user.first_name))
            bot.answerCallbackQuery(text=THUMBS_DOWN_EMOJI,
                                    callback_query_id=update.callback_query.id)

    def set_reminders(self, bot, update):
        print 'reminder'
        time = datetime.today().time()
        if time.hour < 9:
            pass
        threading.Timer(timedelta(minutes=0, seconds=10).total_seconds(),
                        self._groups_daily_timer,
                        args=(self.go_to_gym, )).start()

        threading.Timer(timedelta(minutes=0, seconds=15).total_seconds(),
                        self._groups_daily_timer,
                        args=(self.went_to_gym, )).start()

    def new_group(self, bot, update):
        print 'group'
        new_chat_member = update.message.new_chat_members[0]
        group_id = update.message.chat_id

        if new_chat_member.id == self.updater.bot.id and self.groups.get(group_id) is None:  # bot joined to new group
            group = Group(id=update.message.chat_id)
            self.session.add(group)

    def run(self):
        handlers = (
            CommandHandler('register', self.register_command),  # register
            CommandHandler('mydays', self.my_days_command),  # mydays
            CommandHandler('reminder', self.set_reminders),  # reminder
            MessageHandler(filters=Filters.status_update.new_chat_members, callback=self.new_group),  # new chat
            CallbackQueryHandler(pattern='register.*', callback=self.select_day),  # selected training day
            CallbackQueryHandler(pattern='went_to_gym.*', callback=self.went_to_gym_answer),  # went to gym answer
        )

        for handler in handlers:
            self.dispatcher.add_handler(handler)

        print 'starting to poll'
        self.updater.start_polling()


if __name__ == '__main__':
    updater = Updater(token=TOKEN)
    dispatcher = updater.dispatcher

    GymBot(updater, dispatcher).run()

