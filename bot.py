#!/usr/bin/env python3

import os
import telebot
import mysql.connector
import sys


def setup_database(database):
    cursor = database.cursor()
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


class LeihlisteBot:
    def __init__(self):
        db_info = {
            "host": os.environ.get("DB_HOST"),
            "user": os.environ.get("DB_USER"),
            "password": os.environ.get("DB_PASSWORD"),
        }
        print("init")
        try:
            self.database = mysql.connector.connect(**db_info)
            print("Connected to database.")
        except mysql.connector.errors.DatabaseError:
            sys.exit("Failed to connect do database")

        # TODO maybe handle bot errors?
        self.bot = telebot.TeleBot(os.environ.get("BOT_TOKEN"))

    def run(self):
        self.bot.infinity_polling()

    def _register_message_handler(self, handler, **kwargs):
        self.bot.message_handler(**kwargs)(
            lambda *args, **kwargs2: handler(*args, **kwargs)
        )

    def send_welcome(self, message):
        ids = compute_session_id(message)
        self.bot.reply_to(message, f"YX {ids}")

    def register_handlers(self):
        self._register_message_handler(self.send_welcome)


bot = LeihlisteBot()
bot.register_handlers()
bot.run()
