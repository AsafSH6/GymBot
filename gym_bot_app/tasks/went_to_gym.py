# encoding: utf-8
from __future__ import unicode_literals

from datetime import time, timedelta, datetime

from telegram.ext import CallbackQueryHandler

from gym_bot_app.tasks import Task
from gym_bot_app.utils import trainee_already_marked_training_date, \
    get_trainees_that_selected_today_and_did_not_train_yet
from gym_bot_app.keyboards import yes_or_no_inline_keyboard, YES_RESPONSE
from gym_bot_app.decorators import repeats, run_for_all_groups, get_trainee_and_group
from gym_bot_app import THUMBS_UP_EMOJI, THUMBS_DOWN_EMOJI, FACEPALMING_EMOJI, TROPHY_EMOJI, WEIGHT_LIFTER_EMOJI


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
    TRAINEE_WENT_TO_GYM_MSG = 'כל הכבוד {trainee} יא {creature}!\n Earned {gained_exp} EXP.'
    TRAINEE_DIDNT_GO_TO_GYM_MSG = 'אפס מאופס {trainee}'
    TRAINEE_LEVELED_UP_MSG = 'יא בוט עלית רמה!!\n' + TROPHY_EMOJI + ' {level} ' + TROPHY_EMOJI
    GROUP_LEVELED_UP_MSG = 'כולכם בוטים עליתי רמה!!\n' + WEIGHT_LIFTER_EMOJI + ' {level} ' + WEIGHT_LIFTER_EMOJI

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
            def notify_other_groups(msg, trainee_leveled_up=False, gained_exp=0):
                other_groups = (g for g in trainee.groups if g != group)
                for other_group in other_groups:
                    bot.send_message(chat_id=other_group.id,
                                     text=msg)
                    if trainee_leveled_up:
                        bot.send_message(chat_id=other_group.id,
                                         text=trainee_leveled_up_msg)

                    other_group_leveled_up = other_group.level.gain_exp(exp=gained_exp)
                    if other_group_leveled_up:
                        self.logger.info('Group %s leveled up to level %s', other_group, other_group.level)
                        other_group_leveled_up_msg = self.GROUP_LEVELED_UP_MSG.format(level=other_group.level)
                        bot.send_message(chat_id=other_group.id,
                                         text=other_group_leveled_up_msg)
                    other_group.save()

            if response == YES_RESPONSE:
                self.logger.debug('%s answered yes', trainee.first_name)
                training_info, trainee_leveled_up = trainee.add_training_info(training_date=question_date, trained=True)
                gained_exp = training_info.gained_exp
                self.logger.info('Trainee gained %s EXP', gained_exp)

                msg = self.TRAINEE_WENT_TO_GYM_MSG.format(trainee=trainee.first_name,
                                                          creature=trainee.personal_configurations.creature,
                                                          gained_exp=gained_exp)
                bot.send_message(chat_id=group.id,
                                 text=msg)
                bot.answerCallbackQuery(text=THUMBS_UP_EMOJI,
                                        callback_query_id=update.callback_query.id)

                if trainee_leveled_up:
                    self.logger.info('Trainee %s leveled up to %s', trainee, trainee.level)
                    trainee_leveled_up_msg = self.TRAINEE_LEVELED_UP_MSG.format(level=trainee.level)
                    bot.send_message(chat_id=group.id,
                                     text=trainee_leveled_up_msg)

                group_leveled_up = group.level.gain_exp(exp=gained_exp)
                if group_leveled_up:
                    self.logger.info('Group %s leveled up to level %s', group, group.level)
                    group_leveled_up_msg = self.GROUP_LEVELED_UP_MSG.format(level=group.level)
                    bot.send_message(chat_id=group.id,
                                     text=group_leveled_up_msg)
                trainee.save()
                group.save()
                notify_other_groups(msg, trainee_leveled_up=trainee_leveled_up, gained_exp=gained_exp)
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
