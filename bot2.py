#!/usr/bin/env python3

import os
import telebot
import mysql.connector
import sys
from collections import defaultdict
import datetime
from telebot import types

class Q:
    def __init__(self, question, callback, next_q):
        self.question = question
        self.callback = callback
        self.next_q = next_q

class Bot:
    def __init__(self):
        # TODO maybe handle bot errors?
        self.bot = telebot.TeleBot(os.environ.get("BOT_TOKEN"))
        self.handlers = defaultdict(lambda: None)
        self.bot.message_handler(commands=["add"])(self.add_command)
        self.bot.message_handler(func=lambda _: True)(self.on_message)

    def run(self):
        self.bot.infinity_polling()

    def on_message(self, message):
        sid = message.chat.id
        if q := self.handlers[sid]:
            del self.handlers[sid]
            q.callback(message)
            if q.next_q is not None:
                q.next_q(message)
            return
        else:
            self.bot.reply_to(message, text=f"Unknown command: {message.text}")

    def add_command(self, message):
        def a(message):
            self.a = int(message.text)

        def b(message):
            self.b = int(message.text)
            self.result = self.a + self.b

        def c(message):
            print("XXX", self.result)
            self.bot.reply_to(message, self.result)

        result = Q("", c, None)
        second = Q("Second number?", b, self.query(result))
        first = Q("First number?", a, self.query(second))
        self.query(first)(message)

    def query(self, q):
        def w(message):
            sid = message.chat.id
            if q.next_q is None:
                q.callback(message)
            else:
                self.handlers[sid] = q
                self.bot.reply_to(message, text=q.question, reply_markup=types.ForceReply())
        return w

bot = Bot()
bot.run()
