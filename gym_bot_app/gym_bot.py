# encoding: utf-8
from __future__ import unicode_literals

import logging
import os

from telegram.ext import Updater

from gym_bot_app.commands import (AdminCommand,
                                  MyDaysCommand,
                                  TrainedCommand,
                                  SelectDaysCommand,
                                  SetCreatureCommand,
                                  MyStatisticsCommand,
                                  BotStatisticsCommand,
                                  AllTrainingTraineesCommand)

from gym_bot_app.tasks import (GoToGymTask,
                               WentToGymTask,
                               NewWeekSelectDaysTask)


MSG_TIMEOUT = 20

logging.basicConfig(filename='logs/gymbot.log',
                    encoding='utf-8',
                    format='%(asctime)s %(levelname)s - [%(module)s:%(funcName)s:%(lineno)d] %(message)s',
                    datefmt='%d-%m-%Y:%H:%M:%S',
                    level=logging.DEBUG)


def run_gym_bot(token, logger):
    updater = Updater(token=token)

    """ Tasks """
    GoToGymTask(updater=updater, logger=logger).start()
    WentToGymTask(updater=updater, logger=logger).start()
    NewWeekSelectDaysTask(updater=updater, logger=logger).start()

    """ Commands """
    AdminCommand(updater=updater, logger=logger).start()
    MyDaysCommand(updater=updater, logger=logger).start()
    TrainedCommand(updater=updater, logger=logger).start()
    SelectDaysCommand(updater=updater, logger=logger).start()
    SetCreatureCommand(updater=updater, logger=logger).start()
    MyStatisticsCommand(updater=updater, logger=logger).start()
    BotStatisticsCommand(updater=updater, logger=logger).start()
    AllTrainingTraineesCommand(updater=updater, logger=logger).start(command_name='all_the_botim')

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
