# encoding: utf-8
from __future__ import unicode_literals

from datetime import time, timedelta

from telegram.ext import CallbackQueryHandler
from telegram.vendor.ptb_urllib3.urllib3 import Timeout

from gym_bot_app import THUMBS_UP_EMOJI, THUMBS_DOWN_EMOJI
from gym_bot_app.keyboards import yes_or_no_inline_keyboard
from gym_bot_app.tasks.task import Task
from gym_bot_app.decorators import repeats, get_trainee, run_for_all_groups


class WentToGymTask(Task):
    TARGET_TIME = time(hour=0, minute=0, second=0, microsecond=0)
    WENT_TO_GYM_QUERY_IDENTIFIER = 'went_to_gym'

    def __init__(self, *args, **kwargs):
        super(WentToGymTask, self).__init__(*args, **kwargs)
        self.dispatcher.add_handler(
            CallbackQueryHandler(pattern='{identifier}.*'.format(identifier=self.WENT_TO_GYM_QUERY_IDENTIFIER),
                                 callback=self.went_to_gym_callback_query)
        )

    def get_start_time(self):
        return self._seconds_until_time(target_time=self.TARGET_TIME)

    @repeats(every_seconds=timedelta(minutes=1).total_seconds())
    @run_for_all_groups
    def execute(self, group):
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

        keyboard = yes_or_no_inline_keyboard(callback_identifier=self.WENT_TO_GYM_QUERY_IDENTIFIER)
        try:
            self.updater.bot.send_message(chat_id=group.id,
                                          text=text,
                                          reply_markup=keyboard)
            self.logger.info('finished to remind to group %s', group)
        except Timeout:
            self.logger.error('Timeout occurred')

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

