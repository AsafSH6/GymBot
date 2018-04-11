# encoding: utf-8
from __future__ import unicode_literals

from datetime import time, timedelta

from telegram import error
from telegram.ext import CallbackQueryHandler
from telegram.vendor.ptb_urllib3.urllib3 import Timeout

from gym_bot_app.keyboards import all_group_participants_select_days_inline_keyboard
from gym_bot_app.tasks.task import Task
from gym_bot_app.decorators import get_trainee_and_group, repeats, run_for_all_groups


class NewWeekSelectDaysTask(Task):
    """Telegram gym bot new week select days task."""
    DEFAULT_TARGET_DAY = 'Saturday'
    DEFAULT_TARGET_TIME = time(hour=21, minute=30, second=0, microsecond=0)

    NEW_WEEK_SELECT_DAYS_CALLBACK_IDENTIFIER = 'new_week'

    def __init__(self, target_day=None, target_time=None, *args, **kwargs):
        super(NewWeekSelectDaysTask, self).__init__(*args, **kwargs)
        self.target_day = target_day or self.DEFAULT_TARGET_DAY
        self.target_time = target_time or self.DEFAULT_TARGET_TIME

        self.updater.dispatcher.add_handler(
            CallbackQueryHandler(pattern='{identifier}.*'.format(identifier=self.NEW_WEEK_SELECT_DAYS_CALLBACK_IDENTIFIER),
                                 callback=self.new_week_selected_day_callback_query)
        )

    def get_start_time(self):
        """Start time of select ne week days task based on the target day and target time."""
        return self._seconds_until_day_and_time(target_day_name=self.target_day,
                                                target_time=self.target_time)

    @repeats(every_seconds=timedelta(weeks=1).total_seconds())
    @run_for_all_groups
    def _execute(self, group):
        """Override method to execute new week select days task.

        Unselect all training days for trainees in group and sends keyboard to select
        training days for the next week.

        """
        self.logger.info('new week remind for %s', group)
        for trainee in group.trainees:
            trainee.unselect_all_days()
        self.logger.info('unselected all days for the trainees in group')

        self.logger.info('generation inline keyboard for new week select days for group %s', group)
        keyboard = all_group_participants_select_days_inline_keyboard(
            group=group,
            callback_identifier=self.NEW_WEEK_SELECT_DAYS_CALLBACK_IDENTIFIER
        )
        try:
            self.updater.bot.send_message(chat_id=group.id,
                                          text='כל הבוטים, מוזמנים למלא את ימי האימון לשבוע הקרוב כדי שתוכלו כבר מעכשיו לחשוב על תירוצים למה לא ללכת',
                                          reply_markup=keyboard)
        except Timeout:
            self.logger.error('Timeout occurred')

    @get_trainee_and_group
    def new_week_selected_day_callback_query(self, bot, update, trainee, group):
        """Response handler of new week select days task.

        In case day was not selected before- mark as selected.
        In case day was selected before- unselect it.

        """
        self.logger.info('new week selected day')
        self.logger.info('trainee selected %s in group %s', trainee, group)
        query = update.callback_query

        _, selected_day_name = query.data.split()
        self.logger.info('selected day name is %s', selected_day_name)
        selected_day = trainee.training_days.get(name=selected_day_name)
        selected_day.selected = not selected_day.selected
        trainee.save()
        group.reload()

        self.logger.info('generation inline keyboard for new week select days for group %s', group)
        keyboard = all_group_participants_select_days_inline_keyboard(
            group=group,
            callback_identifier=self.NEW_WEEK_SELECT_DAYS_CALLBACK_IDENTIFIER
        )
        try:
            bot.edit_message_reply_markup(chat_id=group.id,
                                          message_id=query.message.message_id,
                                          reply_markup=keyboard)
            bot.answerCallbackQuery(text="selected {}".format(selected_day.name.capitalize()),
                                    callback_query_id=update.callback_query.id)
        except error.BadRequest:
            self.logger.debug('The keyboard have not changed probably because the trainee changed it from'
                              ' another keyboard.')
            bot.answerCallbackQuery(text='יא בוט על חלל, כבר שינית את זה במקום אחר...',
                                    callback_query_id=update.callback_query.id)
