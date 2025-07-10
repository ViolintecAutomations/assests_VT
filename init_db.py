import MySQLdb

DB_HOST = 'localhost'
DB_USER = 'root'
DB_PASS = 'Violin@12'
DB_NAME = 'CMS'

# Connect to MySQL server (no DB yet)
conn = MySQLdb.connect(host=DB_HOST, user=DB_USER, passwd=DB_PASS)
cursor = conn.cursor()
cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
cursor.close()
conn.close()

# Now connect to the Asset Management System DB
conn = MySQLdb.connect(host=DB_HOST, user=DB_USER, passwd=DB_PASS, db=DB_NAME)
cursor = conn.cursor()

with open('db_schema.sql', 'r') as f:
    sql = f.read()

for statement in sql.split(';'):
    stmt = statement.strip()
    if stmt:
        try:
            cursor.execute(stmt)
        except Exception as e:
            print(f'Error executing statement: {stmt}\n{e}')

conn.commit()
cursor.close()
conn.close()
print('Asset Management System database initialized.') 