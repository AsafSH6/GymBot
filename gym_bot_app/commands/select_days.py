# encoding: utf-8
from __future__ import unicode_literals
from datetime import datetime

from telegram import ParseMode, error
from telegram.ext import CallbackQueryHandler

from gym_bot_app import DAYS_NAME, LYING_FACE_EMOJI
from gym_bot_app.commands import Command
from gym_bot_app.keyboards import trainee_select_days_inline_keyboard
from gym_bot_app.decorators import get_trainee_and_group


class SelectDaysCommand(Command):
    """Telegram gym bot select days command.

    Sends keyboard that allows to select training days.

    """
    DEFAULT_COMMAND_NAME = 'select_days'
    SELECT_DAYS_QUERY_IDENTIFIER = 'select_days'

    SELECT_DAYS_MSG = 'באיזה ימים אתה מתאמן יא בוט?'
    CANT_CHOOSE_TO_OTHERS_MSG = 'אי אפשר לבחור לאחרים יא בוט'
    CANT_CHOOSE_BEFORE_CURRENT_DAY = 'אי אפשר לבחור יום שכבר חלף יא בוט'
    ALREADY_CHANGED_IN_ANOTHER_PLACE_MSG = 'יא בוט על חלל, כבר שינית את זה במקום אחר...'
    CANCELED_TRAINING_DAY_ON_THE_SAME_DAY = 'אני אולי בוט אבל אני לא אדיוט! {{trainee_name}} ביטל את האימון שלו היום {emoji}'.format(emoji=LYING_FACE_EMOJI)

    def __init__(self, *args, **kwargs):
        super(SelectDaysCommand, self).__init__(*args, **kwargs)
        self.updater.dispatcher.add_handler(
            CallbackQueryHandler(pattern='{identifier}.*'.format(identifier=self.SELECT_DAYS_QUERY_IDENTIFIER),
                                 callback=self.selected_day_callback_query),  # selected training day
        )

    @get_trainee_and_group
    def _handler(self, bot, update, trainee, group):
        """Override method to handle select days command.

        Generate keyboard to select or unselect training days.

        """
        self.logger.info('Select days command with %s in %s', trainee, group)

        keyboard = self.get_select_days_keyboard(trainee=trainee)
        update.message.reply_text(quote=True,
                                  text=self.SELECT_DAYS_MSG,
                                  reply_markup=keyboard)

    @classmethod
    def get_select_days_keyboard(cls, trainee):
        """Get trainee select days inline keyboard of given trainee with SelectDaysCommand query identifier.

        Using this keyboard cause the response to be handled by the SelectDaysCommand response handler.

        Args:
            trainee(models.Trainee): trainee to generate the keyboard for.

        """
        return trainee_select_days_inline_keyboard(trainee=trainee,
                                                   callback_identifier=cls.SELECT_DAYS_QUERY_IDENTIFIER)

    @get_trainee_and_group
    def selected_day_callback_query(self, bot, update, trainee, group):
        """Response handler of select days command.

        In case day was not selected before- mark it as selected.
        In case day was selected before- unselect it.

        """
        self.logger.info('Selected day callback query with %s in %s', trainee, group)

        query = update.callback_query
        _, trainee_id, selected_day = query.data.split()

        if trainee.id != unicode(trainee_id):  # other trainee tried to select days for this trainee
            self.logger.debug('Trainee is not allow to choose for others')
            bot.answerCallbackQuery(text=self.CANT_CHOOSE_TO_OTHERS_MSG,
                                    callback_query_id=update.callback_query.id,
                                    parse_mode=ParseMode.HTML)
            return

        try:
            selected_day = trainee.training_days.get(name=selected_day)
            self.logger.debug('Selected day %s', selected_day)
            today = datetime.today().strftime('%A')
            self.logger.debug('Today is %s', today)
            today_index = DAYS_NAME.index(today)
            selected_day_index = DAYS_NAME.index(selected_day.name)
            if selected_day_index < today_index:
                self.logger.debug('Trainee`s selected day index %s is before current day index %s', selected_day_index, today_index)
                bot.answerCallbackQuery(text=self.CANT_CHOOSE_BEFORE_CURRENT_DAY,
                                    callback_query_id=update.callback_query.id,
                                    parse_mode=ParseMode.HTML)
                return
            selected_day.selected = not selected_day.selected
            updated_keyboard = self.get_select_days_keyboard(trainee=trainee)
            bot.edit_message_reply_markup(chat_id=query.message.chat_id,
                                          message_id=query.message.message_id,
                                          reply_markup=updated_keyboard)
            bot.answerCallbackQuery(text='selected {}'.format(selected_day.name.capitalize()),
                                    callback_query_id=update.callback_query.id)

            # Alert trainees canceled training day on the same day
            # they were supposed to train.
            if (selected_day.selected is False  # Canceled training day.
                    and
                selected_day.name == today):  # The day is today.
                self.logger.debug("Trainee canceled training day on the same day")
                msg = self.CANCELED_TRAINING_DAY_ON_THE_SAME_DAY.format(trainee_name=trainee.first_name)
                bot.send_message(chat_id=group.id,
                                 text=msg)

            trainee.save()  # save to db after the message sent to get better performance
        except error.BadRequest:
            self.logger.debug('The keyboard have not changed probably because the trainee changed it from'
                              ' another keyboard')
            bot.answerCallbackQuery(text=self.ALREADY_CHANGED_IN_ANOTHER_PLACE_MSG,
                                    callback_query_id=update.callback_query.id)