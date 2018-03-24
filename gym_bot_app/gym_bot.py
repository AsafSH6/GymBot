# encoding: utf-8
from __future__ import unicode_literals

import os
import json
import logging
import threading
from datetime import datetime, time, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, Filters, MessageHandler

from gym_bot_app.db.models import Group, Trainee
from utils import upper_first_letter, WEIGHT_LIFTER_EMOJI, THUMBS_DOWN_EMOJI, THUMBS_UP_EMOJI

logging.basicConfig(filename='logs/gymbot.log',
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.DEBUG)


class GymBot(object):
    REMINDER_TIME = time(hour=9, minute=0, second=0)
    CHECK_WHETHER_DONE_TIME = time(hour=21, minute=0, second=0)

    def __init__(self, updater, dispatcher, logger):
        self.updater = updater
        self.dispatcher = dispatcher
        self.logger = logger

    def _generate_inline_keyboard_for_select_days(self, trainee):
        self.logger.info('generation inline keyboard for select days for trainee %s', trainee)

        keyboard = []
        for idx, day in enumerate(trainee.training_days):
            day_name = day.name
            if day.selected:
                day_name += ' ' + WEIGHT_LIFTER_EMOJI

            keyboard.append([InlineKeyboardButton(day_name, callback_data='select_days {id} {idx}'.format(id=trainee.id,
                                                                                                          idx=idx))])

        return InlineKeyboardMarkup(keyboard)

    def select_day_command(self, bot, update):
        self.logger.info('select days command')
        trainee_id = update.effective_user.id
        group_id = update.message.chat_id

        trainee = Trainee.objects.get(id=trainee_id)
        self.logger.info('trainee to select days %s', trainee)
        group = Group.objects.get(id=group_id)
        self.logger.info('the group is %s', group)

        if not group:
            self.logger.info('the group does not exist in DB')
            group = Group.create(group_id=group_id)
            self.logger.info('created group %s', group)

        if trainee is None:  # new trainee.
            self.logger.info('trainee does not exist in the DB')
            trainee = Trainee.objects.create(id=trainee_id, first_name=update.effective_user.first_name)
            self.logger.info('created trainee in DB %s', trainee)
            group.add_trainee(new_trainee=trainee)
            self.logger.info('added the trainee to group')

        elif trainee not in group.trainees:  # trainee exists but new in the current group.
            self.logger.info('trainee was not in the group')
            group.add_trainee(new_trainee=trainee)

        keyboard = self._generate_inline_keyboard_for_select_days(trainee)
        update.message.reply_text('באיזה ימים אתה מתאמן יא בוט?', reply_markup=keyboard)

    def select_day(self, bot, update):
        self.logger.info('select day')
        query = update.callback_query

        trainee = Trainee.objects.get(id=update.effective_user.id)
        self.logger.info('trainee selected %s', trainee)
        _, trainee_id, selected_day_index = query.data.split()

        if trainee is None or trainee.id != unicode(trainee_id):
            self.logger.info('trainee is not allow to choose for others')
            bot.answerCallbackQuery(text='אי אפשר לבחור לאחרים יא בוט',
                                    callback_query_id=update.callback_query.id,
                                    parse_mode=ParseMode.HTML)
            return

        logger.info('selected day index %s', selected_day_index)
        selected_day = trainee.training_days[int(selected_day_index)]
        self.logger.info('selected day %s', selected_day)
        if selected_day.selected:
            self.logger.info('already selected day, removing it from the trainee training days')
        else:
            self.logger.info('new selected day, adding it to the trainee training days')

        selected_day.selected = not selected_day.selected
        trainee.save()

        updated_keyboard = self._generate_inline_keyboard_for_select_days(trainee)
        bot.edit_message_reply_markup(chat_id=query.message.chat_id,
                                      message_id=query.message.message_id,
                                      reply_markup=updated_keyboard)

        bot.answerCallbackQuery(text="selected {}".format(upper_first_letter(selected_day.name)),
                                callback_query_id=update.callback_query.id)

    def my_days_command(self, bot, update):
        self.logger.info('my days command')
        trainee = Trainee.objects.get(id=update.effective_user.id)
        self.logger.info('requested by trainee %s', trainee)
        text = ' '.join(day.name for day in trainee.training_days.filter(selected=True))
        self.logger.info('trainee days %s', text)
        bot.send_message(chat_id=update.message.chat_id,
                         text=text)

    def _groups_daily_timer(self, callback):
        self.logger.info('group daily reminder')
        self.logger.info('callback method: %s', callback.func_name)
        for group in Group.objects.all():
            self.logger.info('checking group %s', group)
            today_name = upper_first_letter(datetime.now().strftime('%A'))
            self.logger.info('the day is %s', today_name)

            relevant_trainees = group.get_trainees_in_day(today_name)
            self.logger.info('relevant trainees are %s', relevant_trainees)

            callback(group, relevant_trainees)

        threading.Timer(timedelta(hours=23, minutes=59, seconds=59).total_seconds(),
                        self._groups_daily_timer,
                        args=(callback, )).start()
        self.logger.info('set %s timer for tomorrow', callback.func_name)

    def go_to_gym(self, group, relevant_trainees):
        self.logger.info('reminding to go to the gym')
        if not relevant_trainees:
            self.logger.info('there are no relevant trainees')
            return
        go_to_gym_plural = 'לכו היום לחדר כושר יא בוטים {training}'
        go_to_gym_individual = 'לך היום לחדר כושר יא בוט {training}'

        training_today_msg = ' '.join('@' + trainee.first_name for trainee in relevant_trainees)

        if len(relevant_trainees) > 1:
            self.logger.info('more than one trainee therefore creating plural msg')
            text = go_to_gym_plural.format(training=training_today_msg)
        else:
            self.logger.info('one trainee creating msg for individual')
            text = go_to_gym_individual.format(training=training_today_msg)

        self.updater.bot.send_message(chat_id=group.id, text=text)
        self.logger.info('finished to remind to group %s', group)

    def went_to_gym(self, group, relevant_trainees):
        self.logger.info('asking who went to the gym')
        self.logger.info('relevant trainees %s', relevant_trainees)
        if not relevant_trainees:
            self.logger.info('there are no relevant trainees')
            return

        went_to_gym_plural = 'הלכתם היום לחדכ יא בוטים? {training}'
        went_to_gym_individual = 'הלכת היום לחדכ יא בוט? {training}'
        training_today_msg = ' '.join('@' + trainee.first_name for trainee in relevant_trainees)

        if len(relevant_trainees) > 1:
            self.logger.info('more than one trainee therefore creating plural msg')
            text = went_to_gym_plural.format(training=training_today_msg)
        else:
            self.logger.info('one trainee creating msg for individual')
            text = went_to_gym_individual.format(training=training_today_msg)

        allowed_trainees = ','.join(unicode(trainee.id) for trainee in relevant_trainees)
        keyboard = [[InlineKeyboardButton('כן',
                                          callback_data='went_to_gym [{allowed_trainees}] yes'.format(
                                              allowed_trainees=allowed_trainees)),
                     InlineKeyboardButton('אני אפס',
                                          callback_data='went_to_gym [{allowed_trainees}] no'.format(
                                              allowed_trainees=allowed_trainees))]]

        self.updater.bot.send_message(chat_id=group.id,
                                      text=text,
                                      reply_markup=InlineKeyboardMarkup(keyboard))
        self.logger.info('finished to remind to group %s', group)

    def went_to_gym_answer(self, bot, update):
        self.logger.info('answer to went to gym question')
        query = update.callback_query
        _, allowed_trainees, answer = query.data.split()
        allowed_trainees = json.loads(allowed_trainees)
        self.logger.info('allowed to answer the question trainees %s', allowed_trainees)
        trainee = Trainee.objects.get(id=update.effective_user.id)
        self.logger.info('the trainee that answered %s', trainee)

        if trainee is None or trainee.id not in allowed_trainees:
            self.logger.info('the trainee is not allowed to answer the question')
            bot.answerCallbackQuery(text='זה לא היום שלך להתאמן יא בוט',
                                    callback_query_id=update.callback_query.id)
            return

        if answer == 'yes':
            self.logger.info('%s %s', trainee.first_name, 'answered yes')
            bot.send_message(chat_id=query.message.chat_id,
                             text='כל הכבוד {trainee} אלוף!'.format(trainee=trainee.first_name))
            bot.answerCallbackQuery(text=THUMBS_UP_EMOJI,
                                    callback_query_id=update.callback_query.id)
        else:
            self.logger.info('%s %s', trainee.first_name, 'answered no')
            bot.send_message(chat_id=query.message.chat_id,
                             text='אפס מאופס {trainee}'.format(trainee=trainee.first_name))
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
            logger.info('preparing remind of %s with args: %s',
                        reminder['method'].func_name,
                        reminder['args'])
            now = datetime.today()
            reminder_time = reminder['time']
            logger.info('requested reminder time is %s', reminder_time)
            desired_datetime = now.replace(hour=reminder_time.hour,
                                           minute=reminder_time.minute,
                                           second=reminder_time.second)
            if now > desired_datetime:  # time already passed- move to the next day.
                logger.info('the time already passed, setting reminder for tomorrow')
                desired_datetime += timedelta(days=1)
            else:
                logger.info('the time did not pass, setting reminder for today')
            logger.info('requested reminder datetime is %s', desired_datetime)

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
        self.logger.info('new group detected')
        new_chat_member = update.message.new_chat_members[0]
        group_id = update.message.chat_id
        self.logger.info('new group id is %s', group_id)
        self.logger.info('new chat member in the group is %s', new_chat_member.first_name)

        if new_chat_member.id == self.updater.bot.id and Group.objects.get(id=group_id) is None:  # bot joined to new group
            self.logger.info('bot joined to new group')
            group = Group.create(group_id=update.message.chat_id)
            self.logger.info('created instance of the new group in the DB %s', group)

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
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        os.environ['BOT_TOKEN'] = os.environ['BOT_TOKEN_TEST']
        os.environ['MONGODB_URL_CON'] = os.environ['MONGODB_URL_CON_TEST']

    token = os.environ['BOT_TOKEN']
    db_con_string = os.environ['MONGODB_URL_CON']

    from mongoengine import connect
    connect(host=os.environ['MONGODB_URL_CON'])

    updater = Updater(token=token)
    dispatcher = updater.dispatcher
    logger = logging.getLogger(__name__)
    logger.addHandler(logging.StreamHandler())

    GymBot(updater, dispatcher, logger).run()
