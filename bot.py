#!/usr/bin/env python3

from collections import defaultdict
from telebot import types
import datetime
import mysql.connector
import os
import re
import sys
import telebot


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
            if handler.callback(message):
                return
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


def format_value(value):
    if isinstance(value, datetime.datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value


class Loan:
    keys = [
        "acceptor",
        "borrower",
        "end_date",
        "lender",
        "loan_id",
        "loan_name",
        "start_date",
        "notes",  # TODO
    ]

    def __init__(self, session_id, **kwargs):
        self.session_id = session_id
        for key in Loan.keys:
            setattr(self, key, kwargs.get(key, None))

        if self.start_date is None and self.lender is not None:
            self.start_date = datetime.datetime.now()

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
        values = tuple(format_value(getattr(self, key)) for key in keys)
        ret = cursor.execute(query, values)
        connection.commit()

    def load(sid, loan_id, connection):
        cursor = connection.cursor(prepared=True)
        query = f"""
            SELECT {', '.join(Loan.keys)}
            FROM leihliste
            WHERE loan_id=%s
        """
        values = (loan_id,)
        cursor.execute(query, values)
        values = cursor.fetchone()
        kwargs = {k: v for k, v in zip(Loan.keys, values)}
        kwargs["loan_id"] = loan_id
        return Loan(sid, **kwargs)

    def get_loan_id_from_uuid(uuid):
        pattern = ".*\(#(\d+)\)$"
        match = re.match(pattern, uuid)
        if match is None:
            print(f"Failed to get loan_id from uuid '{uuid}'.")
        return match[1]

    def uuid(self):
        return f"{self.loan_name} (#{self.loan_id})"

    def __str__(self):
        def format_timestamp(timestamp):
            time = timestamp.strftime("%H:%M")
            date = timestamp.strftime("%d.%m.%Y")
            return f"um *{time}* am *{date}*"

        def status():
            if self.end_date is None:
                return "Noch nicht zurückgegeben"
            else:
                return f"Zurückgegeben {format_timestamp(self.end_date)} an *{self.acceptor}*"

        return "\n".join(
            [
                f"> *{self.loan_name}*",
                f"Verliehen {format_timestamp(self.start_date)} an *{self.borrower}*.",
                f"Ausgegeben von *{self.lender}*.",
                f"{status()}.",
                f"_{self.notes or 'keine Notiz'}_",
            ]
        )

    def finish(self, connection, full_user):
        cursor = connection.cursor(prepared=True)
        keys = ["end_date", "acceptor"]
        kvs = ", ".join(f"{key} = %s" for key in keys)
        query = f"""
            UPDATE leihliste
            SET {kvs}
            WHERE loan_id=%s
        """
        values = (
            datetime.datetime.now(),
            get_user_name(full_user),
            int(self.loan_id),
        )
        values = tuple(map(format_value, values))
        cursor.execute(query, values)


def get_user_name(full_user):
    if full_user.first_name is not None:
        if full_user.last_name is not None:
            return f"{full_user.first_name} {full_user.last_name}"
        return full_user.first_name
    if full_user.last_name is not None:
        return full_user.last_name
    return full_user.username



def compute_session_id(message):
    return str(message.chat.id)


class DatabaseWrapper():
    def __init__(self, database_config):
        self.database_config = database_config
        self.database = None

    def _connect(self):
        try:
            self.database = mysql.connector.connect(**self.database_config)
            print("Connected to database.")
        except mysql.connector.errors.DatabaseError:
            sys.exit("Failed to connect do database")

    def cursor(self, *args, **kwargs):
        if not self.database:
            self._connect()
        try:
            return self.database.cursor()
        except mysql.connector.errors.OperationalError:
            print("Connection timed out. Reconnecting ...")
            self._connect()
            return self.database.cursor()


class LeihlisteBot(Bot):
    cancel_text = "abbrechen"

    def __init__(self, database):
        super().__init__()
        self.bot.message_handler(commands=["verleihen"])(self.verleihen)
        self.bot.message_handler(commands=["list_ausstehend"])(self.list_pending_loans)
        self.bot.message_handler(commands=["list_zurueckgegeben"])(
            self.list_completed_loans
        )
        self.bot.message_handler(commands=["list_alle"])(self.list_all_loans)
        self.bot.message_handler(commands=["rueckgabe"])(self.return_loan)
        self.polish()
        self.database = database
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
            loan.store(self.database)
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

    def pending_loads_keyboard(self, sid):
        keyboard = types.ReplyKeyboardMarkup(
            row_width=1,
            resize_keyboard=True,
            one_time_keyboard=True,
            is_persistent=False,
        )
        loans = self.get_loans(sid, pending=True, completed=False)
        if len(loans) == 0:
            self.bot.reply_to(message, "Keine offenen Leihen.")
            self.state = "idle"
            return

        keyboard.add(types.KeyboardButton(LeihlisteBot.cancel_text))
        for loan in loans:
            keyboard.add(types.KeyboardButton(loan.uuid()))
        return keyboard

    def return_loan(self, message):
        sid = compute_session_id(message)

        def query_loan(message):
            if message.text == LeihlisteBot.cancel_text:
                self.bot.reply_to(message, "Abbruch.")
                return True
            sid = compute_session_id(message)
            loan_uuid = message.text
            self.active_loans[sid] = Loan.load(
                sid, Loan.get_loan_id_from_uuid(loan_uuid), self.database
            )

        def complete_loan(message):
            sid = compute_session_id(message)
            loan = self.active_loans[sid]
            loan.finish(self.database, message.from_user)
            self.bot.reply_to(
                message,
                text=str(loan),
                reply_markup=types.ReplyKeyboardRemove(),
                parse_mode="markdown",
            )

        self.query_list(
            message,
            [
                Query(
                    query_loan,
                    text="Wähle die Position die zurückgegeben werden soll",
                    reply_markup=self.pending_loads_keyboard(sid),
                ),
                Query(complete_loan),
            ],
        )

    def get_loans(self, sid, pending, completed):
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
        SELECT loan_id
        FROM leihliste
        WHERE session_id='{sid}' {condition}
        """
        cursor = self.database.cursor()
        cursor.execute(query)
        return [
            Loan.load(sid, loan_id, self.database)
            for loan_id, in cursor.fetchall()
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


db_info = {
    "host": os.environ.get("DB_HOST"),
    "user": os.environ.get("DB_USER"),
    "password": os.environ.get("DB_PASSWORD"),
    "database": os.environ.get("DB_NAME"),
    "port": int(os.environ.get("DB_PORT")),
}

database = DatabaseWrapper(db_info)
bot = LeihlisteBot(database)
bot.run()
