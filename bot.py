#!/usr/bin/env python3

import os
import telebot
import mysql.connector
import sys
from collections import defaultdict
import datetime
from telebot import types


def setup_database(cursor):
    cursor.execute(
        """
        create table leihliste(
            loan_id int auto_increment,
            loan_name varchar(255) not null,
            start_date date,
            end_date date,
            borrower varchar(255),
            lender varchar(255),
            session_id varchar(255),
            primary key(loan_id)
        )"""
    )


def compute_session_id(message):
    return f"{message.chat.id}:{message.reply_to_message.message_thread_id}"


def format_date(timestamp):
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")


class Loan:
    def __init__(self, session_id, **kwargs):
        keys = [
            "borrower",
            "end_date",
            "lender",
            "loan_id",
            "loan_name",
            "session_id",
            "start_date",
            "notes",
        ]
        for key in keys:
            setattr(self, key, kwargs.get(key, None))

        if self.start_date is None and lender is not None:
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
        print("insert values: ")
        for k, v in zip(keys, values):
            print(f"{k}: {v}")
        connection.commit()
        return True

    def __str__(self):
        def status():
            if self.end_date is None:
                return "noch nicht zurückgegeben"
            else:
                time = self.end_date.strftime("%H:%M")
                date = self.end_date.strftime("%d.%m.%Y")
                return f"z̈́urückgegeben um {time} am {date}"

        return "\n".join(
            [
                f"> *_{self.loan_name}_*",
                f"Ausgeliehen am *{self.start_date}* von *{self.borrower}*.",
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


class LeihlisteBot:
    def __init__(self):
        db_info = {
            "host": os.environ.get("DB_HOST"),
            "user": os.environ.get("DB_USER"),
            "password": os.environ.get("DB_PASSWORD"),
            "database": os.environ.get("DB_NAME"),
            "port": int(os.environ.get("DB_PORT")),
        }
        print("init")
        try:
            self.db_connection = mysql.connector.connect(**db_info)
            print("Connected to database.")
        except mysql.connector.errors.DatabaseError:
            sys.exit("Failed to connect do database")

        # TODO maybe handle bot errors?
        self.bot = telebot.TeleBot(os.environ.get("BOT_TOKEN"))
        self.active_loans = defaultdict(lambda: None)

    def query(self, message, question):
        self.bot.reply_to(message, text=question, reply_markup=types.ForceReply())

    def run(self):
        self.bot.infinity_polling()

    def get_current_loan(self, message):
        return self.active_loans[compute_session_id(message)]

    def handle_new_loan(self, message):
        current_loan = self.get_current_loan(message)
        if current_loan is None:
            sid = compute_session_id(message)
            self.active_loans[sid] = Loan(sid, get_user_name(message.from_user))
            self.query(message, "Was willst du verleihen?")
            return

        if current_loan.loan_name is None:
            current_loan.loan_name = message.text
            print("set loan name: ", message.text)
            self.query(message, f"Wer will {current_loan.loan_name} ausleihen?")
            return

        if current_loan.borrower is None:
            current_loan.borrower = message.text
            if current_loan.store(self.db_connection):
                self.bot.reply_to(message, f"Alles klar, ist gespeichert!")
            else:
                self.bot.reply_to(
                    message,
                    f"Da ist was schief gegangen, der Verleihvorgang wird abgebrochen.",
                )
                del self.active_loans[sid]

    def handle_return(self, message):
        current_loan = self.get_current_loan(message)
        if current_loan is None:
            self.bot.reply_to(
                message, "Wähle die Position die zurückgegeben werden soll"
            )
            sid = compute_session_id(message)
            self.active_loans[sid] = Loan(sid)
        else:
            self.bot.reply_to(message, "TODO")
            del self.active_loans[sid]

    def any_message(self, message):
        current_loan = self.get_current_loan(message)
        if current_loan is None:
            self.bot.reply_to(
                message, f"The command {message.text} is not known. TODO help text."
            )
        elif current_loan.is_in_database():
            self.handle_return(message)
        else:
            self.handle_new_loan(message)

    def list_loans(self, message, pending, completed):
        sid = compute_session_id(message)
        keys = ["loan_name", "start_date", "borrower", "lender"]
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
        loans = [
            Loan(sid, **{k: v for k, v in zip(keys, values)})
            for values in cursor.fetchall()
        ]
        count = "keine" if len(loans) == 0 else str(len(loans))
        text = f"{label}: {count}\n" + "\n\n".join(map(str, loans))
        print(text)
        self.bot.reply_to(message, text, parse_mode="markdown")

    def list_pending_loans(self, message):
        self.list_loans(message, pending=True, completed=False)

    def list_all_loans(self, message):
        self.list_loans(message, pending=True, completed=True)

    def list_completed_loans(self, message):
        self.list_loans(message, pending=False, completed=True)

    def register_handlers(self):
        self.bot.message_handler(commands=["verleihen"])(self.handle_new_loan)
        self.bot.message_handler(commands=["list_ausstehend"])(self.list_pending_loans)
        self.bot.message_handler(commands=["list_zurueckgegeben"])(self.list_completed_loans)
        self.bot.message_handler(commands=["list_alle"])(self.list_all_loans)
        self.bot.message_handler(commands=["rueckgabe"])(self.handle_return)
        self.bot.message_handler(func=lambda _: True)(self.any_message)


bot = LeihlisteBot()
bot.register_handlers()
bot.run()
