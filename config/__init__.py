"""Use PyMySQL with Django's MySQL backend on every entry point."""
import pymysql

pymysql.install_as_MySQLdb()
