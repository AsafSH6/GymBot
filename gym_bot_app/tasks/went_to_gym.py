# encoding: utf-8
from __future__ import unicode_literals

from datetime import time, timedelta

from telegram.ext import CallbackQueryHandler
from telegram.vendor.ptb_urllib3.urllib3 import Timeout

from gym_bot_app import THUMBS_UP_EMOJI, THUMBS_DOWN_EMOJI
from gym_bot_app.keyboards import yes_or_no_inline_keyboard, YES_RESPONSE
from gym_bot_app.tasks import Task
from gym_bot_app.decorators import repeats, get_trainee, run_for_all_groups


class WentToGymTask(Task):
    """Telegram gym bot went to gym task."""
    DEFAULT_TARGET_TIME = time(hour=21, minute=0, second=0, microsecond=0)
    WENT_TO_GYM_QUERY_IDENTIFIER = 'went_to_gym'

    WENT_TO_GYM_PLURAL_MSG = 'הלכתם היום לחדכ יא בוטים? {training}'
    WENT_TO_GYM_INDIVIDUAL_MSG = 'הלכת היום לחדכ יא בוט? {training}'
    NOT_YOUR_DAY_TO_TRAINE_MSG = 'זה לא היום שלך להתאמן יא בוט'
    TRAINEE_WENT_TO_GYM_MSG = 'כל הכבוד {trainee} אלוף!'
    TRAINEE_DIDNT_GO_TO_GYM_MSG = 'אפס מאופס {trainee}'

    def __init__(self, target_time=None, *args, **kwargs):
        super(WentToGymTask, self).__init__(*args, **kwargs)
        self.target_time = target_time or self.DEFAULT_TARGET_TIME

        self.updater.dispatcher.add_handler(
            CallbackQueryHandler(pattern='{identifier}.*'.format(identifier=self.WENT_TO_GYM_QUERY_IDENTIFIER),
                                 callback=self.went_to_gym_callback_query)
        )

    def get_start_time(self):
        """Start time of went to gym task based on the target time."""
        return self._seconds_until_time(target_time=self.target_time)

    @repeats(every_seconds=timedelta(days=1).total_seconds())
    @run_for_all_groups
    def _execute(self, group):
        """Override method to execute went to gym task.

        Sends went to gym message with the trainees of today to the given group chat.

        Notes:
            Includes inline keyboard with yes/no answers which is handled by went_to_gym_callback_query.

        """
        self.logger.info('Executing went to gym task with %s', group)

        relevant_trainees = group.get_trainees_of_today()
        self.logger.debug('Relevant trainees %s', relevant_trainees)

        if not relevant_trainees:
            self.logger.debug('There are no relevant trainees')
            return

        try:
            went_to_gym_msg = self._get_went_to_gym_msg(trainees=relevant_trainees)
            keyboard = yes_or_no_inline_keyboard(callback_identifier=self.WENT_TO_GYM_QUERY_IDENTIFIER)
            self.updater.bot.send_message(chat_id=group.id,
                                          text=went_to_gym_msg,
                                          reply_markup=keyboard)
        except Timeout:
            self.logger.error('Timeout occurred')

    @get_trainee
    def went_to_gym_callback_query(self, bot, update, trainee):
        """Response handler of went to gym task.

        Sends message to the trainee based on the response.

        """
        self.logger.info('Went to gym callback query with %s', trainee)

        query = update.callback_query
        _, response, day_name = query.data.split()
        self.logger.debug('Trainee that answered %s and selected day was %s', trainee, day_name)

        if trainee.is_training_in_day(day_name) is False:
            self.logger.debug('Trainee is not allowed to answer the question')
            bot.answerCallbackQuery(text=self.NOT_YOUR_DAY_TO_TRAINE_MSG,
                                    callback_query_id=update.callback_query.id)
            return

        if response == YES_RESPONSE:
            self.logger.debug('%s answered yes', trainee.first_name)
            bot.send_message(chat_id=query.message.chat_id,
                             text=self.TRAINEE_WENT_TO_GYM_MSG.format(trainee=trainee.first_name))
            bot.answerCallbackQuery(text=THUMBS_UP_EMOJI,
                                    callback_query_id=update.callback_query.id)
        else:
            self.logger.debug('%s answered no', trainee.first_name)
            bot.send_message(chat_id=query.message.chat_id,
                             text=self.TRAINEE_DIDNT_GO_TO_GYM_MSG.format(trainee=trainee.first_name))
            bot.answerCallbackQuery(text=THUMBS_DOWN_EMOJI,
                                    callback_query_id=update.callback_query.id)

    def _get_went_to_gym_msg(self, trainees):
        """Generate went to gym message based on the given trainees.

        Args:
            trainees(list): trainees that will be included in the message.

        Returns:
            str. message of went to gym with the given trainees.

        """
        training_today_msg = ' '.join(trainee.first_name for trainee in trainees)

        if len(trainees) > 1:
            self.logger.debug('More than one trainee therefore creating plural msg')
            went_go_gym_msg = self.WENT_TO_GYM_PLURAL_MSG.format(training=training_today_msg)
        else:
            self.logger.debug('One trainee creating msg for individual')
            went_go_gym_msg = self.WENT_TO_GYM_INDIVIDUAL_MSG.format(training=training_today_msg)

        return went_go_gym_msg
