# encoding: utf-8
from __future__ import unicode_literals

from datetime import time, timedelta, datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler

from gym_bot_app import THUMBS_UP_EMOJI, THUMBS_DOWN_EMOJI
from gym_bot_app.models import Group
from gym_bot_app.tasks.task import Task
from gym_bot_app.decorators import repeats, get_trainee


class WentToGymTask(Task):
    TARGET_TIME = time(hour=0, minute=0, second=0, microsecond=0)

    def __init__(self, *args, **kwargs):
        super(WentToGymTask, self).__init__(*args, **kwargs)
        self.dispatcher.add_handler(CallbackQueryHandler(pattern='went_to_gym.*',
                                                         callback=self.went_to_gym_callback_query))

    def get_start_time(self):
        return self._seconds_until_time(target_time=self.TARGET_TIME)

    @repeats(every_seconds=timedelta(minutes=1).total_seconds())
    def execute(self):
        self.logger.info('asking who went to the gym')
        for group in Group.objects:
            self.logger.info('checking group %s', group)
            relevant_trainees = group.get_trainees_of_today()
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

            keyboard = self._generate_inline_keyboard_for_went_to_gym()

            self.updater.bot.send_message(chat_id=group.id,
                                          text=text,
                                          reply_markup=keyboard)
            self.logger.info('finished to remind to group %s', group)

    @get_trainee
    def went_to_gym_callback_query(self, bot, update, trainee):
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
            self.logger.info('%s answered yes', trainee.first_name)
            bot.send_message(chat_id=query.message.chat_id,
                             text='כל הכבוד {trainee} אלוף!'.format(trainee=trainee.first_name))
            bot.answerCallbackQuery(text=THUMBS_UP_EMOJI,
                                    callback_query_id=update.callback_query.id)
        else:
            self.logger.info('%s answered no', trainee.first_name)
            bot.send_message(chat_id=query.message.chat_id,
                             text='אפס מאופס {trainee}'.format(trainee=trainee.first_name))
            bot.answerCallbackQuery(text=THUMBS_DOWN_EMOJI,
                                    callback_query_id=update.callback_query.id)

    def _generate_inline_keyboard_for_went_to_gym(self):
        today_name = datetime.now().strftime('%A')
        keyboard = [[InlineKeyboardButton('כן',
                                          callback_data='went_to_gym yes {today}'.format(today=today_name)),
                     InlineKeyboardButton('אני אפס',
                                          callback_data='went_to_gym no {today}'.format(today=today_name))]]

        return InlineKeyboardMarkup(keyboard)
