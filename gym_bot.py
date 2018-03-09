# encoding: utf-8
from __future__ import unicode_literals

import os
import json
import logging
import threading
from datetime import datetime, time, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, Filters, MessageHandler

from models import User, Group, Day
from utils import get_db_session, upper_first_letter, WEIGHT_LIFTER_EMOJI, DAYS_NAME, THUMBS_DOWN_EMOJI, THUMBS_UP_EMOJI

logging.basicConfig(filename='logs/gymbot.log',
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)


class GymBot(object):
    REMINDER_TIME = time(hour=9, minute=0)
    CHECK_WHETHER_DONE_TIME = time(hour=21, minute=0)

    def __init__(self, db_session, updater, dispatcher, logger):
        self.updater = updater
        self.dispatcher = dispatcher
        self.session = db_session
        self.users = self.session.query(User)
        self.groups = self.session.query(Group)
        self.days = self.session.query(Day)
        self.logger = logger

    def _generate_inline_keyboard_for_select_days(self, user):
        self.logger.info('generation inline keyboard for select days for user %s', user)
        already_selected_days = user.days

        keyboard = []
        for idx, day in enumerate(self.days.all()):
            day_name = upper_first_letter(day.name)
            if day in already_selected_days:
                day_name += ' ' + WEIGHT_LIFTER_EMOJI
            keyboard.append([InlineKeyboardButton(day_name, callback_data='select_days {id} {idx}'.format(id=user.id,
                                                                                                       idx=idx))])

        return InlineKeyboardMarkup(keyboard)

    def select_day_command(self, bot, update):
        self.logger.info('select days command')
        user_id = update.effective_user.id
        group_id = update.message.chat_id

        user = self.users.get(user_id)
        self.logger.info('user to select days %s', user)
        group = self.groups.get(group_id)
        self.logger.info('the group is %s', group)

        if not group:
            self.logger.info('the group does not exist in DB')
            group = Group(id=group_id)
            self.session.add(group)

        if user is None:  # new user.
            self.logger.info('user does not exist in the DB')
            user = User(id=user_id, first_name=update.effective_user.first_name)
            self.session.add(user)
            self.logger.info('created user in DB %s', user)
            group.users.append(user)
            self.logger.info('added the user to group')

        elif user not in group.users:  # user exists but new in the current group.
            self.logger.info('user was not in the group')
            group.users.append(user)

        keyboard = self._generate_inline_keyboard_for_select_days(user)
        update.message.reply_text('באיזה ימים אתה מתאמן יא בוט?', reply_markup=keyboard)

    def select_day(self, bot, update):
        self.logger.info('select day')
        query = update.callback_query

        user = self.users.get(update.effective_user.id)
        self.logger.info('user selected %s', user)
        _, user_id, selected_day_index = query.data.split()

        if user is None or user.id != int(user_id):
            self.logger.info('user is not allow to choose for others')
            bot.answerCallbackQuery(text='אי אפשר לבחור לאחרים יא בוט',
                                    callback_query_id=update.callback_query.id,
                                    parse_mode=ParseMode.HTML)
            return

        selected_day = DAYS_NAME[int(selected_day_index)]
        selected_day = self.days.get(selected_day)
        self.logger.info('selected day %s', selected_day)
        if user not in selected_day.users:
            self.logger.info('new selected day, adding it to the user training days')
            selected_day.users.append(user)
        else:
            self.logger.info('already selected day- removing it from the user training days')
            selected_day.users.remove(user)
        self.session.commit()

        updated_keyboard = self._generate_inline_keyboard_for_select_days(user)
        bot.edit_message_reply_markup(chat_id=query.message.chat_id,
                                      message_id=query.message.message_id,
                                      reply_markup=updated_keyboard)

        bot.answerCallbackQuery(text="selected {}".format(upper_first_letter(selected_day.name)),
                                callback_query_id=update.callback_query.id)

    def my_days_command(self, bot, update):
        self.logger.info('my days command')
        user = self.users.get(update.effective_user.id)
        self.logger.info('asking user %s', user)
        text = ' '.join(unicode(day) for day in user.days)
        self.logger.info('user days %s', text)
        bot.send_message(chat_id=update.message.chat_id,
                         text=text)

    def _groups_daily_timer(self, callback):
        self.logger.info('group daily reminder')
        self.logger.info('callback method: %s', callback.func_name)
        for group in self.groups.all():
            self.logger.info('checking group %s %s %s', group, 'with users', group.users)
            today_name = datetime.now().strftime('%A').lower()
            today = self.days.get(today_name)
            self.logger.info('the day is %s', today)

            # TODO: use sql query.
            relevant_users = [user for user in today.users if user in group.users]
            self.logger.info('relevant users are %s', relevant_users)

            callback(group, relevant_users)

    def go_to_gym(self, group, relevant_users):
        self.logger.info('reminding to go to the gym')
        if not relevant_users:
            self.logger.info('there are no relevant users')
            return
        go_to_gym_plural = 'לכו היום לחדר כושר יא בוטים {training}'
        go_to_gym_individual = 'לך היום לחדר כושר יא בוט {training}'

        training_today_msg = ' '.join('@' + user.first_name for user in relevant_users)

        if len(relevant_users) > 1:
            self.logger.info('more than one user therefore creating plural msg')
            text = go_to_gym_plural.format(training=training_today_msg)
        else:
            self.logger.info('one user creating msg for individual')
            text = go_to_gym_individual.format(training=training_today_msg)

        self.updater.bot.send_message(chat_id=group.id, text=text)
        self.logger.info('finished to remind to group %s', group)
        threading.Timer(timedelta(hours=23, minutes=59, seconds=45).total_seconds(),
                        self._groups_daily_timer,
                        args=(self.went_to_gym, ))
        self.logger.info('set go to gym timer for tomorrow')

    def went_to_gym(self, group, relevant_users):
        self.logger.info('asking who went to the gym')
        self.logger.info('relevant users %s', relevant_users)
        if not relevant_users:
            self.logger.info('there are no relevant users')
            return

        went_to_gym_plural = 'הלכתם היום לחדכ יא בוטים? {training}'
        went_to_gym_individual = 'הלכת היום לחדכ יא בוט? {training}'
        training_today_msg = ' '.join('@' + user.first_name for user in relevant_users)

        if len(relevant_users) > 1:
            self.logger.info('more than one user therefore creating plural msg')
            text = went_to_gym_plural.format(training=training_today_msg)
        else:
            self.logger.info('one user creating msg for individual')
            text = went_to_gym_individual.format(training=training_today_msg)

        allowed_users = ','.join(unicode(user.id) for user in relevant_users)
        keyboard = [[InlineKeyboardButton('כן',
                                    callback_data='went_to_gym [{allowed_users}] yes'.format(
                                    allowed_users=allowed_users)),
                     InlineKeyboardButton('אני אפס',
                                          callback_data='went_to_gym [{allowed_users}] no'.format(
                                          allowed_users=allowed_users))]]

        self.updater.bot.send_message(chat_id=group.id,
                                      text=text,
                                      reply_markup=InlineKeyboardMarkup(keyboard))
        self.logger.info('finished to remind to group %s', group)
        threading.Timer(timedelta(hours=23, minutes=59, seconds=45).total_seconds(),
                        self._groups_daily_timer,
                        args=(self.went_to_gym, ))
        self.logger.info('set went to gym timer for tomorrow')

    def went_to_gym_answer(self, bot, update):
        self.logger.info('answer to went to gym question')
        query = update.callback_query
        _, allowed_users, answer = query.data.split()
        allowed_users = [int(user_id) for user_id in json.loads(allowed_users)]
        self.logger.info('allowed to answer the question users %s', allowed_users)
        user = self.users.get(update.effective_user.id)
        self.logger.info('the user that answered %s', user)

        if not user or user.id not in allowed_users:
            self.logger.info('the user is not allowed to answer the question')
            bot.answerCallbackQuery(text='זה לא היום שלך להתאמן יא בוט',
                                    callback_query_id=update.callback_query.id)
            return
        if answer == 'yes':
            self.logger.info('%s %s', user.first_name, 'answered yes')
            bot.send_message(chat_id=query.message.chat_id,
                             text='כל הכבוד {user} אלוף!'.format(user=user.first_name))
            bot.answerCallbackQuery(text=THUMBS_UP_EMOJI,
                                    callback_query_id=update.callback_query.id)
        else:
            self.logger.info('%s %s', user.first_name, 'answered no')
            bot.send_message(chat_id=query.message.chat_id,
                             text='אפס מאופס {user}'.format(user=user.first_name))
            bot.answerCallbackQuery(text=THUMBS_DOWN_EMOJI,
                                    callback_query_id=update.callback_query.id)

    def set_reminders(self):
        self.logger.info('setting reminders')
        reminders = [
            {
                'method': self._groups_daily_timer,
                'time': self.REMINDER_TIME,
                'args': (self.go_to_gym, )
            },
            {
                'method': self._groups_daily_timer,
                'time': self.CHECK_WHETHER_DONE_TIME,
                'args': (self.went_to_gym, )
            },
        ]

        for reminder in reminders:
            now = datetime.today()
            reminder_time = reminder['time']
            desired_datetime = now.replace(hour=reminder_time.hour,
                                           minute=reminder_time.minute)
            if now > desired_datetime:  # time already passed- move to the next day.
                desired_datetime += timedelta(days=1)

            seconds_to_wait = (desired_datetime - now).total_seconds()

            self.logger.info('%s seconds until %s with args: %s',
                             seconds_to_wait,
                             reminder['method'].func_name,
                             reminder['args'])

            threading.Timer(seconds_to_wait,
                            reminder['method'],
                            args=reminder['args']).start()

        self.logger.info('set all reminders')

    def new_group(self, bot, update):
        self.logger.info('new group detected with id')
        new_chat_member = update.message.new_chat_members[0]
        group_id = update.message.chat_id
        self.logger.info('new group id is %s', group_id)
        self.logger.info('new chat member in the group is %s', new_chat_member.first_name)

        if new_chat_member.id == self.updater.bot.id and self.groups.get(group_id) is None:  # bot joined to new group
            self.logger.info('bot joined to new group')
            group = Group(id=update.message.chat_id)
            self.session.add(group)
            self.logger.info('created instance of the new group in the DB')

    def run(self):
        self.logger.info('starting to run')
        handlers = (
            CommandHandler('select_days', self.select_day_command),  # select days
            CommandHandler('mydays', self.my_days_command),  # mydays
            MessageHandler(filters=Filters.status_update.new_chat_members, callback=self.new_group),  # new chat
            CallbackQueryHandler(pattern='select_days.*', callback=self.select_day),  # selected training day
            CallbackQueryHandler(pattern='went_to_gym.*', callback=self.went_to_gym_answer),  # went to gym answer
        )

        for handler in handlers:
            self.dispatcher.add_handler(handler)

        self.set_reminders()
        self.logger.info('starting to poll')
        self.updater.start_polling()


if __name__ == '__main__':
    token = os.environ['BOT_TOKEN']
    db_con_string = os.environ['POSTGRES_URL_CON']

    updater = Updater(token=token)
    dispatcher = updater.dispatcher
    logger = logging.getLogger(__name__)
    logger.addHandler(logging.StreamHandler())

    db_session = get_db_session(db_con_string)
    GymBot(db_session, updater, dispatcher, logger).run()
