"""Create or repair the local application's MySQL account using a root prompt."""
import argparse
import getpass
import os
from pathlib import Path
import re

import MySQLdb
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def read_configuration():
    load_dotenv(ROOT / ".env", override=False)
    config = {
        "host": os.environ.get("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.environ.get("MYSQL_PORT", "3306")),
        "database": os.environ.get("MYSQL_DATABASE", "atelier_pc"),
        "user": os.environ.get("MYSQL_USER", "atelier_pc"),
        "password": os.environ.get("MYSQL_PASSWORD", ""),
    }
    if config["host"] not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("Cet assistant est destiné au serveur MySQL de votre PC. Pour un serveur hébergé, utilisez son tableau de bord.")
    if not 1 <= config["port"] <= 65535:
        raise ValueError("MYSQL_PORT doit être un port valide.")
    for key in ("database", "user"):
        maximum = 64 if key == "database" else 32
        if not re.fullmatch(r"[A-Za-z0-9_]{1," + str(maximum) + r"}", config[key]):
            raise ValueError(f"Le paramètre {key} doit contenir uniquement des lettres, chiffres ou caractères soulignés.")
    if config["user"].lower() == "root" or config["database"].lower() in ("mysql", "sys", "information_schema", "performance_schema"):
        raise ValueError("Utilisez une base et un compte propres au projet, par exemple atelier_pc.")
    if config["password"] in ("", "CHANGE_ME", "TON_MOT_DE_PASSE", "ton_mot_de_passe", "le_meme_mot_de_passe_que_dans_le_script_SQL"):
        raise ValueError("Renseignez d’abord MYSQL_PASSWORD dans .env avec le mot de passe choisi pour l’application.")
    return config


def connect(config, *, administrator_password=None):
    options = {
        "host": config["host"], "port": config["port"],
        "charset": "utf8mb4", "connect_timeout": 10,
    }
    if administrator_password is not None:
        options.update(user="root", passwd=administrator_password)
    else:
        options.update(user=config["user"], passwd=config["password"], db=config["database"])
    return MySQLdb.connect(**options)


def configure_mysql(config, administrator_password):
    admin = connect(config, administrator_password=administrator_password)
    try:
        admin.autocommit(True)
        with admin.cursor() as cursor:
            # The database identifier has been restricted to letters, digits and _.
            database = "`" + config["database"] + "`"
            account = (config["user"], "localhost")
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {database} CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
            cursor.execute("CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s", (*account, config["password"]))
            # CREATE USER IF NOT EXISTS alone leaves an existing password unchanged.
            cursor.execute("ALTER USER %s@%s IDENTIFIED BY %s ACCOUNT UNLOCK", (*account, config["password"]))
            cursor.execute(f"GRANT ALL PRIVILEGES ON {database}.* TO %s@%s", account)
    finally:
        admin.close()
    check_connection(config)


def check_connection(config):
    connection = connect(config)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            assert cursor.fetchone()[0] == 1
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description="Créer ou réparer le compte MySQL du projet à partir de .env, sans supprimer ses données.")
    parser.add_argument("--check", action="store_true", help="Vérifier la connexion sans modifier le compte ni demander le mot de passe root.")
    args = parser.parse_args()
    try:
        config = read_configuration()
        if args.check:
            check_connection(config)
            print("Connexion MySQL du projet : OK.")
            return
        print("Le mot de passe de l’application sera synchronisé avec MYSQL_PASSWORD dans .env.")
        print("Les données existantes seront conservées. Le mot de passe root ne sera pas enregistré.")
        administrator_password = getpass.getpass("Mot de passe root MySQL choisi pendant l’installation : ")
        configure_mysql(config, administrator_password)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    except MySQLdb.Error as error:
        code = error.args[0] if error.args else "inconnu"
        if code == 1045:
            message = "Connexion refusée. Vérifiez le mot de passe root de l’installation" if not args.check else "Le compte du projet ne correspond pas encore aux paramètres .env. Lancez cet assistant sans --check"
        elif code in (2002, 2003):
            message = "Serveur inaccessible. Vérifiez le service MySQL et MYSQL_HOST/MYSQL_PORT"
        elif code == 1819:
            message = "Le mot de passe MYSQL_PASSWORD ne satisfait pas la politique MySQL. Choisissez un mot de passe plus fort dans .env"
        else:
            message = "MySQL a refusé la configuration du compte du projet"
        raise SystemExit(f"{message} (code {code}).") from None
    except (EOFError, KeyboardInterrupt):
        raise SystemExit("Configuration annulée.") from None
    print("Compte MySQL configuré et connexion vérifiée.")
    print("Vous pouvez maintenant lancer :")
    print(r".\.venv\Scripts\python.exe manage.py migrate")


if __name__ == "__main__":
    main()
