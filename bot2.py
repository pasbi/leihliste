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


class Loan:
    def __init__(self, session_id, **kwargs):
        self.session_id = session_id
        keys = [
            "borrower",
            "end_date",
            "lender",
            "loan_id",
            "loan_name",
            "start_date",
            "notes",
        ]
        for key in keys:
            setattr(self, key, kwargs.get(key, None))

        if self.start_date is None and self.lender is not None:
            self.start_date = datetime.datetime.now()

    def is_in_database(self):
        return self.loan_id is not None

    def is_closed(self):
        return self.end_date is not None

    def is_constructed(self):
        return self.borrower is not None and self.loan_name is not None

    def is_empty(self):
        return self.lender is None or self.start_date is None

    def store(self, connection):
        cursor = connection.cursor(prepared=True)
        keys = ["borrower", "lender", "loan_name", "session_id", "start_date"]
        query = f"""
            INSERT
            INTO leihliste
            ({", ".join(keys)})
            VALUES
            ({", ".join(["%s"] * len(keys))})
            """
        values = tuple(getattr(self, key) for key in keys)
        ret = cursor.execute(query, values)
        connection.commit()

    def uuid(self):
        return f"{self.loan_name} [{self.loan_id}]"

    def __str__(self):
        def format_timestamp(timestamp):
            time = timestamp.strftime("%H:%M")
            date = timestamp.strftime("%d.%m.%Y")
            return f"um {time} am {date}"

        def status():
            if self.end_date is None:
                return "noch nicht zurückgegeben"
            else:
                return f"z̈́urückgegeben {format_timestamp(self.end_date)}"

        return "\n".join(
            [
                f"> *_{self.loan_name}_*",
                f"Ausgeliehen am *{format_timestamp(self.start_date)}* von *{self.borrower}*.",
                f"Ausgegeben von *{self.lender}*.",
                f"Status: *{status()}*",
                f"_{self.notes or 'keine Notiz'}_",
            ]
        )


def get_user_name(full_user):
    if full_user.first_name is not None:
        if full_user.last_name is not None:
            return f"{full_user.first_name} {full_user.last_name}"
        return full_user.first_name
    if full_user.last_name is not None:
        return full_user.last_name
    return full_user.username


def setup_database():
    db_info = {
        "host": os.environ.get("DB_HOST"),
        "user": os.environ.get("DB_USER"),
        "password": os.environ.get("DB_PASSWORD"),
        "database": os.environ.get("DB_NAME"),
        "port": int(os.environ.get("DB_PORT")),
    }
    try:
        db_connection = mysql.connector.connect(**db_info)
        print("Connected to database.")
        return db_connection
    except mysql.connector.errors.DatabaseError:
        sys.exit("Failed to connect do database")


def compute_session_id(message):
    return str(message.chat.id)


class LeihlisteBot(Bot):
    def __init__(self):
        super().__init__()
        self.bot.message_handler(commands=["verleihen"])(self.verleihen)
        self.polish()
        self.db_connection = setup_database()
        self.active_loans = defaultdict(lambda: None)

    def verleihen(self, message):
        def query_loan_name(message):
            sid = compute_session_id(message)
            self.active_loans[sid] = Loan(
                sid, loan_name=message.text, lender=get_user_name(message.from_user)
            )

        def query_borrower(message):
            sid = compute_session_id(message)
            self.active_loans[sid].borrower = message.text

        def commit_new_loan(message):
            sid = compute_session_id(message)
            loan = self.active_loans[sid]
            loan.store(self.db_connection)
            text = f"Alles klar, neue Ausleihe wurde gespeichert!\n{loan}"
            self.bot.reply_to(message, text, parse_mode="markdown")

        self.query_list(
            message,
            [
                Query(query_loan_name, text="Was wird ausgeliehen?"),
                Query(query_borrower, text="An wen wird verliehen?"),
                Query(commit_new_loan),
            ],
        )


bot = LeihlisteBot()
bot.run()
