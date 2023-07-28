#!/usr/bin/env python3

import os
import telebot
import mysql.connector
import sys
from collections import defaultdict
import datetime
from telebot import types


class Query:
    def __init__(self, callback, **kwargs):
        self.kwargs = kwargs
        self.callback = callback
        self.next_step = None


class Bot:
    def __init__(self):
        # TODO maybe handle bot errors?
        self.bot = telebot.TeleBot(os.environ.get("BOT_TOKEN"))
        self.handlers = defaultdict(lambda: None)

    def polish(self):
        self.bot.message_handler(func=lambda _: True)(self.on_message)

    def run(self):
        self.bot.infinity_polling()

    def on_message(self, message):
        sid = message.chat.id
        if handler := self.handlers[sid]:
            del self.handlers[sid]
            handler.callback(message)
            if handler.next_step is not None:
                handler.next_step(message)
            return
        else:
            self.bot.reply_to(message, text=f"Unknown command: {message.text}")

    def query(self, handler):
        def w(message):
            sid = message.chat.id
            if handler.next_step is None:
                handler.callback(message)
            else:
                self.handlers[sid] = handler
                kwargs = handler.kwargs
                kwargs.setdefault("reply_markup", types.ForceReply())
                self.bot.reply_to(message, **kwargs)

        return w

    def query_list(self, message, qs):
        for i in range(len(qs) - 1):
            qs[i].next_step = self.query(qs[i + 1])
        self.query(qs[0])(message)


class LeihlisteBot(Bot):
    def __init__(self):
        super().__init__()
        self.bot.message_handler(commands=["add"])(self.add_command)
        self.polish()

    def add_command(self, message):
        def a(message):
            self.a = int(message.text)

        def b(message):
            self.b = int(message.text)
            self.result = self.a + self.b

        def c(message):
            self.bot.reply_to(message, self.result)

        keyboard = types.ReplyKeyboardMarkup(
            row_width=1,
            resize_keyboard=True,
            one_time_keyboard=True,
            is_persistent=True,
        )
        keyboard.add(types.KeyboardButton("99"))
        keyboard.add(types.KeyboardButton("76"))

        self.query_list(
            message,
            [
                Query(a, text="First number?", reply_markup=keyboard),
                Query(b, text="Second number?"),
                Query(c),
            ],
        )


bot = LeihlisteBot()
bot.run()
