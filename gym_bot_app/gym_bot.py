# encoding: utf-8
from __future__ import unicode_literals

import os
import logging
import threading
from datetime import datetime, time, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ParseMode, error
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, Filters, MessageHandler

from gym_bot_app.models import Group, Day
from gym_bot_app.decorators import get_trainee, get_group, get_trainee_and_group
from gym_bot_app.utils import upper_first_letter
from gym_bot_app import WEIGHT_LIFTER_EMOJI, THUMBS_DOWN_EMOJI, THUMBS_UP_EMOJI

logging.basicConfig(filename='logs/gymbot.log',
                    encoding='utf-8',
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)


class GymBot(object):
    REMINDER_TIME = time(hour=9, minute=0, second=0)
    CHECK_WHETHER_DONE_TIME = time(hour=21, minute=0, second=0)
    NEW_WEEK_SELECT_DAYS = time(hour=21, minute=45, second=0)  # TODO: change to datetime and select saturday.

    def __init__(self, updater, dispatcher, logger):
        self.updater = updater
        self.dispatcher = dispatcher
        self.logger = logger

    def _generate_inline_keyboard_for_select_days(self, trainee):
        self.logger.info('generation inline keyboard for select days for trainee %s', trainee)

        keyboard = []
        for day in trainee.training_days:
            training_day = day.name

            if day.selected:
                training_day += ' ' + WEIGHT_LIFTER_EMOJI

            callback_data = 'select_days {id} {day_name}'.format(id=trainee.id, day_name=day.name)
            keyboard.append([InlineKeyboardButton(training_day, callback_data=callback_data)])

        return InlineKeyboardMarkup(keyboard)

    def _generate_inline_keyboard_for_new_week_select_days(self, group):
        self.logger.info('generation inline keyboard for new week select days for group %s', group)
        keyboard = []
        for day in Day.get_week_days():
            training_in_day = day.name

            trainees = group.get_trainees_in_day(day.name)
            if trainees:
                training_in_day += ': ' + ', '.join(trainee.first_name
                                                    for trainee in trainees)

            callback_data = 'new_week {day_name}'.format(day_name=day.name)
            keyboard.append([InlineKeyboardButton(training_in_day, callback_data=callback_data)])

        return InlineKeyboardMarkup(keyboard)

    @get_trainee_and_group
    def select_day_command(self, bot, update, trainee, group):
        self.logger.info('select days command')
        self.logger.info('trainee to select days %s', trainee)
        self.logger.info('the group is %s', group)

        keyboard = self._generate_inline_keyboard_for_select_days(trainee)
        update.message.reply_text('באיזה ימים אתה מתאמן יא בוט?', reply_markup=keyboard)

    @get_trainee
    def select_day(self, bot, update, trainee):
        self.logger.info('select day')
        self.logger.info('trainee selected %s', trainee)

        query = update.callback_query
        _, trainee_id, selected_day = query.data.split()

        if trainee.id != unicode(trainee_id):
            self.logger.info('trainee is not allow to choose for others')
            bot.answerCallbackQuery(text='אי אפשר לבחור לאחרים יא בוט',
                                    callback_query_id=update.callback_query.id,
                                    parse_mode=ParseMode.HTML)
            return

        logger.info('selected day %s', selected_day)
        selected_day = trainee.training_days.get(name=selected_day)
        self.logger.info('selected day %s', selected_day)
        if selected_day.selected:
            self.logger.info('already selected day, removing it from the trainee training days')
        else:
            self.logger.info('new selected day, adding it to the trainee training days')
        selected_day.selected = not selected_day.selected
        updated_keyboard = self._generate_inline_keyboard_for_select_days(trainee)

        try:
            bot.edit_message_reply_markup(chat_id=query.message.chat_id,
                                          message_id=query.message.message_id,
                                          reply_markup=updated_keyboard)
            bot.answerCallbackQuery(text='selected {}'.format(upper_first_letter(selected_day.name)),
                                    callback_query_id=update.callback_query.id)
        except error.BadRequest:
            self.logger.debug('The keyboard have not changed probably because the trainee changed it from'
                              ' another keyboard.')
            bot.answerCallbackQuery(text='יא בוט על חלל, כבר שינית את זה במקום אחר...',
                                    callback_query_id=update.callback_query.id)

        trainee.save()

    @get_trainee
    def my_days_command(self, bot, update, trainee):
        self.logger.info('my days command')
        self.logger.info('requested by trainee %s', trainee)
        training_days = ', '.join(day.name for day in trainee.training_days.filter(selected=True))
        if training_days:
            self.logger.info('trainee days %s', training_days)
            bot.send_message(chat_id=update.message.chat_id,
                             reply_to_message_id=update.message.message_id,
                             text=training_days)
        else:
            self.logger.info('trainee does not have any training days')
            training_days = 'לא בחרת ימים להתאמן יא בוט. קח תתפנק'
            bot.send_message(chat_id=update.message.chat_id,
                             reply_to_message_id=update.message.message_id,
                             text=training_days,
                             reply_markup=self._generate_inline_keyboard_for_select_days(trainee))

    @get_group
    def all_the_bots_command(self, bot, update, group):
        days_and_trainees = []
        for day in Day.get_week_days():
            trainees_in_day = group.get_trainees_in_day(day.name)

            if trainees_in_day:
                trainees_names = ', '.join(trainee.first_name for trainee in trainees_in_day)
            else:
                trainees_names = 'None'

            text = '{day_name}: {trainees}'.format(day_name=day.name,
                                                   trainees=trainees_names)
            days_and_trainees.append(text)

        bot.send_message(chat_id=update.message.chat_id,
                         text='\n'.join(days_and_trainees))

    def _groups_daily_timer(self, callback):
        self.logger.info('group daily reminder')
        self.logger.info('callback method: %s', callback.func_name)
        for group in Group.objects.all():
            self.logger.info('checking group %s', group)
            today_name = datetime.now().strftime('%A')
            self.logger.info('the day is %s', today_name)

            relevant_trainees = group.get_trainees_in_day(today_name)
            self.logger.info('relevant trainees are %s', relevant_trainees)

            callback(group, relevant_trainees)

        threading.Timer(timedelta(hours=23, minutes=59, seconds=59).total_seconds(),
                        self._groups_daily_timer,
                        args=(callback, )).start()
        self.logger.info('set %s timer for tomorrow', callback.func_name)

    def new_week_select_days(self):
        self.logger.info('reminding to select days for new week')
        for group in Group.objects:
            self.logger.info('new week remind for %s', group)
            for trainee in group.trainees:
                trainee.unselect_all_days()
            self.logger.info('unselected all days for the trainees in group')

            keyboard = self._generate_inline_keyboard_for_new_week_select_days(group)
            self.updater.bot.send_message(chat_id=group.id,
                                          text='כל הבוטים, מוזמנים למלא את ימי האימון לשבוע הקרוב כדי שתוכלו כבר מעכשיו לחשוב על תירוצים למה לא ללכת',
                                          reply_markup=keyboard)

        threading.Timer(timedelta(weeks=1).total_seconds(),
                        self.new_week_select_days).start()

    @get_trainee_and_group
    def new_week_selected_day(self, bot, update, trainee, group):
        self.logger.info('new week selected day')
        self.logger.info('trainee selected %s in group %s', trainee, group)
        query = update.callback_query

        _, selected_day_name = query.data.split()
        self.logger.info('selected day name is %s', selected_day_name)
        selected_day = trainee.training_days.get(name=selected_day_name)
        selected_day.selected = not selected_day.selected
        trainee.save()
        group.reload()

        keyboard = self._generate_inline_keyboard_for_new_week_select_days(group)
        try:
            bot.edit_message_reply_markup(chat_id=group.id,
                                          message_id=query.message.message_id,
                                          reply_markup=keyboard)
            bot.answerCallbackQuery(text="selected {}".format(upper_first_letter(selected_day.name)),
                                    callback_query_id=update.callback_query.id)
        except error.BadRequest:
            self.logger.debug('The keyboard have not changed probably because the trainee changed it from'
                              ' another keyboard.')
            bot.answerCallbackQuery(text='יא בוט על חלל, כבר שינית את זה במקום אחר...',
                                    callback_query_id=update.callback_query.id)

    def go_to_gym(self, group, relevant_trainees):
        self.logger.info('reminding to go to the gym')
        self.logger.info('relevant trainees %s', relevant_trainees)
        if not relevant_trainees:
            self.logger.info('there are no relevant trainees')
            return

        go_to_gym_plural = 'לכו היום לחדר כושר יא בוטים {training}'
        go_to_gym_individual = 'לך היום לחדר כושר יא בוט {training}'

        training_today_msg = ' '.join(trainee.first_name for trainee in relevant_trainees)

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

        training_today_msg = ' '.join(trainee.first_name for trainee in relevant_trainees)

        if len(relevant_trainees) > 1:
            self.logger.info('more than one trainee therefore creating plural msg')
            text = went_to_gym_plural.format(training=training_today_msg)
        else:
            self.logger.info('one trainee creating msg for individual')
            text = went_to_gym_individual.format(training=training_today_msg)

        today_name = datetime.now().strftime('%A')
        keyboard = [[InlineKeyboardButton('כן',
                                          callback_data='went_to_gym yes {today}'.format(today=today_name)),
                     InlineKeyboardButton('אני אפס',
                                          callback_data='went_to_gym no {today}'.format(today=today_name))]]

        self.updater.bot.send_message(chat_id=group.id,
                                      text=text,
                                      reply_markup=InlineKeyboardMarkup(keyboard))
        self.logger.info('finished to remind to group %s', group)

    @get_trainee
    def went_to_gym_answer(self, bot, update, trainee):
        self.logger.info('answer to went to gym question')
        query = update.callback_query
        _, answer, day_name = query.data.split()
        self.logger.info('the trainee that answered %s', trainee)
        self.logger.info('the day is %s', day_name)

        if trainee.is_training_in_day(day_name) is False:
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
            {
                'method': self.new_week_select_days,
                'time': self.NEW_WEEK_SELECT_DAYS,
                'args': tuple([])
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
            group = Group.objects.create(id=update.message.chat_id)
            self.logger.info('created instance of the new group in the DB %s', group)

    def run(self):
        self.logger.info('starting to run')
        handlers = (
            CommandHandler('select_days', self.select_day_command),  # select days
            CommandHandler('mydays', self.my_days_command),  # mydays
            CommandHandler('all_the_botim', self.all_the_bots_command),  # mydays
            MessageHandler(filters=Filters.status_update.new_chat_members, callback=self.new_group),  # new chat
            CallbackQueryHandler(pattern='select_days.*', callback=self.select_day),  # selected training day
            CallbackQueryHandler(pattern='went_to_gym.*', callback=self.went_to_gym_answer),  # went to gym answer
            CallbackQueryHandler(pattern='new_week.*', callback=self.new_week_selected_day),  # new week select day answer
        )

        for handler in handlers:
            self.dispatcher.add_handler(handler)

        self.set_reminders()
        self.logger.info('starting to poll')
        self.updater.start_polling()
        self.updater.idle()


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
