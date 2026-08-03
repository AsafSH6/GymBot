FROM python:3.8-slim

WORKDIR /app

# TZ is load-bearing: the four daily tasks are scheduled in this timezone
# (gym_bot_app/tasks/task.py reads TZ), and tzdata is not in the slim base image.
ENV TZ=Asia/Jerusalem \
    PYTHONPATH=/app/ \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata \
 && apt-get clean \
 && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
 && echo $TZ > /etc/timezone

COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY gym_bot_app gym_bot_app

# gym_bot.py logs to logs/gymbot.log relative to WORKDIR. It creates the directory
# itself now, but keeping it here means the path exists no matter what.
RUN mkdir -p /app/logs

# Fail the build, not the deploy, if the timezone data ever goes missing.
RUN python3 -c "import time; assert time.tzname[0] in ('IST', 'IDT'), time.tzname"

CMD ["python3", "gym_bot_app/gym_bot.py"]
