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
    return timestamp.strftime('%Y-%m-%d %H:%M:%S')

class Loan:
    store_query = """
        INSERT
        INTO leihliste
        (borrower, lender, loan_name, session_id, start_date)
        VALUES
        (%s, %s, %s, %s, %s)
        """

    def __init__(self, lender=None):
        self.borrower = None
        self.end_date = None
        self.lender = lender
        self.loan_id = None
        self.loan_name = None
        self.session_id = None
        self.start_date = None if lender is None else datetime.datetime.now()
        self.notes = None

    def is_in_database(self):
        return self.loan_id is not None

    def is_closed(self):
        return self.end_date is not None

    def is_constructed(self):
        return self.borrower is not None and self.loan_name is not None

    def is_empty(self):
        return self.lender is None or self.start_date is None

    def store(self, connection, cursor):
        ret = cursor.execute(Loan.store_query, (self.borrower, self.lender, self.loan_name, self.session_id, format_date(self.start_date)))
        connection.commit()
        return True


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
            self.db_cursor = self.db_connection.cursor(prepared=True)
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
            self.active_loans[sid] = Loan(message.from_user.id)
            self.query(message, "Was willst du verleihen?")
            return

        if current_loan.loan_name is None:
            current_loan.loan_name = message.text
            print("set loan name: ", message.text)
            self.query(message, f"Wer will {current_loan.loan_name} ausleihen?")
            return

        if current_loan.borrower is None:
            current_loan.borrower = message.text
            if current_loan.store(self.db_connection, self.db_cursor):
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
            self.active_loans[sid] = Loan()
        else:
            self.bot.reply_to(message, "TODO")
            del self.active_loans[sid]

    def any_message(self, message):
        print(f"any message: {message.text}")
        current_loan = self.get_current_loan(message)
        if current_loan is None:
            self.bot.reply_to(
                message, f"The command {message.text} is not known. TODO help text."
            )
        elif current_loan.is_in_database():
            self.handle_return(message)
        else:
            self.handle_new_loan(message)

    def list_pending_loans(self, message):
        self.bot.reply_to(message, "TODO get all loans...")

    def list_all_loans(self, message):
        self.bot.reply_to(message, "TODO get all loans...")

    def register_handlers(self):
        self.bot.message_handler(commands=["verleihen"])(self.handle_new_loan)
        self.bot.message_handler(commands=["list"])(self.list_pending_loans)
        self.bot.message_handler(commands=["list_all"])(self.list_all_loans)
        self.bot.message_handler(commands=["rückgabe"])(self.handle_return)
        self.bot.message_handler(func=lambda _: True)(self.any_message)


bot = LeihlisteBot()
bot.register_handlers()
bot.run()
