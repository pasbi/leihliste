# leihliste

A Telegram Bot to administer a Leihliste (German for list of borrowed things).
The whole bot is in German, if you want me to translate it: open an issue.

## Installation
1. Create a new bot using BotFather
3. Clone this repo
4. Create a virtual environment using requirements.txt
5. Create a database (MySQL, MariaDB, or similar), use `leihliste.sql` to initialize it.
6. Create a .env file:
   ```
    export BOT_TOKEN=The bot token you get from BotFather
    export DB_HOST=The host name of your database
    export DB_USER=The username of your database
    export DB_PASSWORD=The password for your database
    export DB_NAME=The name of your database
    export DB_PORT=The port of your database
    ```
7. Activate the environment and source the .env file
8. Run the bot: `./bot.py`

The script must run forever, when you stop it, the bot will stop working, so it's best to deploy it to some machine that is always on.

## Usage
All commands are interactive, they require no arguments.
The bot will ask for additional information if required.

- `/verleihen`: Create a new loan, the bot will ask for a name and who's borrowing it.
The lender is the user issuing this command, the lend timestamp is also automatically inserted.
- `/list_ausstehend` list all loas that have not been returned yet.
- `/list_zurueckgegeben` list all loans that were returned already.
- `/list_alle` list all loans.
- `/rueckgabe` Return a loan, a list of not yet returned items will be displayed so the user can pick an item interactively.
