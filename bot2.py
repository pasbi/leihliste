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
        return f"{self.loan_name} (@{self.loan_id})"

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
        self.bot.message_handler(commands=["list_ausstehend"])(self.list_pending_loans)
        self.bot.message_handler(commands=["list_zurueckgegeben"])(
            self.list_completed_loans
        )
        self.bot.message_handler(commands=["list_alle"])(self.list_all_loans)
        self.bot.message_handler(commands=["rueckgabe"])(self.return_loan)
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

    def return_loan(self, message):
        keyboard = types.ReplyKeyboardMarkup(
            row_width=1,
            resize_keyboard=True,
            one_time_keyboard=True,
            is_persistent=False,
        )
        sid = compute_session_id(message)
        loans = self.get_loans(sid, pending=True, completed=False)
        if len(loans) == 0:
            self.bot.reply_to(message, "Keine offenen Leihen.")
            self.state = "idle"
            return
        keyboard.add(types.KeyboardButton("abbrechen"))
        for loan in loans:
            keyboard.add(types.KeyboardButton(loan.uuid()))

        def query_loan(message):
            sid = compute_session_id(message)
            self.active_loans[sid] = None

        def debug(message):
            loan = 42
            self.bot.reply_to(
                message,
                f"selected loan: {loan}",
                reply_markup=types.ReplyKeyboardRemove(),
            )

        self.query_list(
            message,
            [
                Query(
                    query_loan,
                    text="Wähle die Position die zurückgegeben werden soll",
                    reply_markup=keyboard,
                ),
                Query(debug),
            ],
        )

    def get_loans(self, sid, pending, completed):
        keys = ["loan_name", "start_date", "borrower", "lender", "loan_id"]
        if pending and completed:
            condition = ""
            label = "Ausgeliehene und zurückgegebene Objekte"
        elif pending:
            condition = "AND end_date is NULL"
            label = "Ausgeliehene Objekte"
        elif completed:
            condition = "AND end_date is not NULL"
            label = "Zurückgegebene Objekte"
        else:
            sys.exit("weird condition.")
        query = f"""
        SELECT {", ".join(keys)}
        FROM leihliste
        WHERE session_id='{sid}' {condition}
        """
        cursor = self.db_connection.cursor()
        cursor.execute(query)
        return [
            Loan(sid, **{k: v for k, v in zip(keys, values)})
            for values in cursor.fetchall()
        ]

    def list_loans(self, message, pending, completed):
        if pending and completed:
            label = "Ausgeliehene und zurückgegebene Objekte"
        elif pending:
            label = "Ausgeliehene Objekte"
        elif completed:
            label = "Zurückgegebene Objekte"
        sid = compute_session_id(message)
        loans = self.get_loans(sid, pending, completed)
        count = "keine" if len(loans) == 0 else str(len(loans))
        text = f"{label}: {count}\n" + "\n\n".join(map(str, loans))
        self.bot.reply_to(message, text, parse_mode="markdown")

    def list_pending_loans(self, message):
        self.list_loans(message, pending=True, completed=False)

    def list_all_loans(self, message):
        self.list_loans(message, pending=True, completed=True)

    def list_completed_loans(self, message):
        self.list_loans(message, pending=False, completed=True)


bot = LeihlisteBot()
bot.run()
