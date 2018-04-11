# encoding: utf-8
from __future__ import unicode_literals

import logging
import os

from telegram.ext import Updater

from gym_bot_app.commands.all_the_bots import AllTheBotsCommand
from gym_bot_app.commands.my_days import MyDaysCommand
from gym_bot_app.commands.select_days import SelectDaysCommand
from gym_bot_app.tasks import (GoToGymTask,
                               NewWeekSelectDaysTask,
                               WentToGymTask,
                               )


MSG_TIMEOUT = 20

logging.basicConfig(filename='logs/gymbot.log',
                    encoding='utf-8',
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)


def run_gym_bot(token, logger):
    updater = Updater(token=token)

    GoToGymTask(updater=updater, logger=logger).start()
    WentToGymTask(updater=updater, logger=logger).start()
    NewWeekSelectDaysTask(updater=updater, logger=logger).start()
    SelectDaysCommand(updater=updater, logger=logger).start()
    MyDaysCommand(updater=updater, logger=logger).start()
    AllTheBotsCommand(updater=updater, logger=logger).start(command_name='all_the_botim')

    updater.start_polling(timeout=MSG_TIMEOUT)
    updater.idle()


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        os.environ['BOT_TOKEN'] = os.environ['BOT_TOKEN_TEST']
        os.environ['MONGODB_URL_CON'] = os.environ['MONGODB_URL_CON_TEST']

    token = os.environ['BOT_TOKEN']
    db_con_string = os.environ['MONGODB_URL_CON']

    from mongoengine import connect
    connect(host=db_con_string)

    logger = logging.getLogger(__name__)
    logger.addHandler(logging.StreamHandler())

    run_gym_bot(token, logger)

