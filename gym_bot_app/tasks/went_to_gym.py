# encoding: utf-8
from __future__ import unicode_literals

from datetime import time, timedelta, datetime

from telegram.ext import CallbackQueryHandler

from gym_bot_app.tasks import Task
from gym_bot_app.utils import trainee_already_marked_training_date, \
    get_trainees_that_selected_today_and_did_not_train_yet
from gym_bot_app.keyboards import yes_or_no_inline_keyboard, YES_RESPONSE
from gym_bot_app.decorators import repeats, run_for_all_groups, get_trainee_and_group
from gym_bot_app import THUMBS_UP_EMOJI, THUMBS_DOWN_EMOJI, FACEPALMING_EMOJI


class WentToGymTask(Task):
    """Telegram gym bot went to gym task."""
    DEFAULT_TARGET_TIME = time(hour=21, minute=0, second=0, microsecond=0)
    WENT_TO_GYM_QUERY_IDENTIFIER = 'went_to_gym'

    DATE_FORMAT = '%d/%m/%Y'

    YES_BUTTON_OPTION_TEXT = 'כן'
    NO_BUTTON_OPTION_TEXT = 'אני אפס'
    NOT_YOUR_DAY_TO_TRAIN_MSG = 'זה לא היום שלך להתאמן יא בוט'
    ALREADY_ANSWERED_WENT_TO_GYM_QUESTION_MSG = 'כבר ענית על השאלה יא בוט {}'.format(FACEPALMING_EMOJI)
    WENT_TO_GYM_PLURAL_MSG = 'הלכתם היום לחדכ יא בוטים? {trainees}'
    WENT_TO_GYM_INDIVIDUAL_MSG = 'הלכת היום לחדכ יא בוט? {trainees}'
    TRAINEE_WENT_TO_GYM_MSG = 'כל הכבוד {trainee} יא {creature}!'
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
    def execute(self, group):
        """Override method to execute went to gym task.

        Sends went to gym message with the trainees of today to the given group chat.

        Notes:
            Includes inline keyboard with yes/no answers which is handled by went_to_gym_callback_query.

        """
        self.logger.info('Executing went to gym task with %s', group)

        relevant_trainees = get_trainees_that_selected_today_and_did_not_train_yet(group)
        self.logger.debug('Relevant trainees %s', relevant_trainees)

        if relevant_trainees:
            went_to_gym_msg = self._get_went_to_gym_msg(trainees=relevant_trainees)
            went_to_gym_keyboard = self.get_went_to_gym_keyboard()
            self.updater.bot.send_message(chat_id=group.id,
                                          text=went_to_gym_msg,
                                          reply_markup=went_to_gym_keyboard)
        else:
            self.logger.debug('There are no relevant trainees')

    @get_trainee_and_group
    def went_to_gym_callback_query(self, bot, update, trainee, group):
        """Response handler of went to gym task.

        Sends message to the trainee and adds training day info based on the response.

        """
        self.logger.info('Went to gym callback query with %s in %s', trainee, group)

        query = update.callback_query
        _, response, question_date = query.data.split()
        question_date = datetime.strptime(question_date, self.DATE_FORMAT).date()
        self.logger.debug('Answered by %s and selected day was %s', trainee, question_date)

        if trainee.is_training_in_day(day_name=question_date.strftime('%A')) is False:
            self.logger.debug('Trainee is not allowed to answer the question')
            bot.answerCallbackQuery(text=self.NOT_YOUR_DAY_TO_TRAIN_MSG,
                                    callback_query_id=update.callback_query.id)
        elif trainee_already_marked_training_date(trainee=trainee, training_date=question_date):
            self.logger.debug('Trainee already answered to went to gym question')
            bot.answerCallbackQuery(text=self.ALREADY_ANSWERED_WENT_TO_GYM_QUESTION_MSG,
                                    callback_query_id=update.callback_query.id)
        else:
            def notify_other_groups(msg):
                other_groups = (g for g in trainee.groups if g != group)
                for other_group in other_groups:
                    bot.send_message(chat_id=other_group.id,
                                     text=msg)

            if response == YES_RESPONSE:
                self.logger.debug('%s answered yes', trainee.first_name)
                msg = self.TRAINEE_WENT_TO_GYM_MSG.format(trainee=trainee.first_name,
                                                          creature=trainee.personal_configurations.creature)
                bot.send_message(chat_id=group.id,
                                 text=msg)
                bot.answerCallbackQuery(text=THUMBS_UP_EMOJI,
                                        callback_query_id=update.callback_query.id)
                trainee.add_training_info(training_date=question_date, trained=True)
                notify_other_groups(msg)
            else:
                self.logger.debug('%s answered no', trainee.first_name)
                msg = self.TRAINEE_DIDNT_GO_TO_GYM_MSG.format(trainee=trainee.first_name)
                bot.send_message(chat_id=group.id,
                                 text=self.TRAINEE_DIDNT_GO_TO_GYM_MSG.format(trainee=trainee.first_name))
                bot.answerCallbackQuery(text=THUMBS_DOWN_EMOJI,
                                        callback_query_id=update.callback_query.id)
                trainee.add_training_info(training_date=question_date, trained=False)
                notify_other_groups(msg)

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
            went_go_gym_msg = self.WENT_TO_GYM_PLURAL_MSG.format(trainees=training_today_msg)
        else:
            self.logger.debug('One trainee creating msg for individual')
            went_go_gym_msg = self.WENT_TO_GYM_INDIVIDUAL_MSG.format(trainees=training_today_msg)

        return went_go_gym_msg

    @classmethod
    def get_went_to_gym_keyboard(cls):
        return yes_or_no_inline_keyboard(callback_identifier=cls.WENT_TO_GYM_QUERY_IDENTIFIER,
                                         yes_option=cls.YES_BUTTON_OPTION_TEXT,
                                         no_option=cls.NO_BUTTON_OPTION_TEXT,
                                         date_format=cls.DATE_FORMAT)
