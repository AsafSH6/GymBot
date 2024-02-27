FROM python:3.8

WORKDIR /app

EXPOSE 8080

COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY gym_bot_app gym_bot_app
COPY logs logs

ENV PYTHONPATH=/app/

CMD ["python3", "gym_bot_app/gym_bot.py"]
