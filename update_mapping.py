import pymysql

config = dict(host='localhost', user='root', password='Violin@12', db='CMS', cursorclass=pymysql.cursors.DictCursor, autocommit=True)

def has_column(cur, table, col):
    try:
        cur.execute(f"SHOW COLUMNS FROM `{table}` LIKE %s", (col,))
        return cur.fetchone() is not None
    except Exception:
        return False

def main():
    conn = pymysql.connect(**config)
    cur = conn.cursor()
    try:
        cur.execute("SET SQL_SAFE_UPDATES=0")
        # Ensure asset_types id 59 -> System
        cur.execute("INSERT INTO asset_types (id, name) VALUES (59, 'System') ON DUPLICATE KEY UPDATE name='System'")

        # pr_items mapping
        if has_column(cur, 'pr_items', 'asset_type_id'):
            cur.execute("""
                UPDATE pr_items pri
                JOIN asset_types t ON pri.asset_type_id = t.id
                SET pri.asset_type_id = 59
                WHERE LOWER(t.name) IN ('system','systems')
            """)

        # assets mapping (if asset_type_id present)
        if has_column(cur, 'assets', 'asset_type_id'):
            cur.execute("""
                UPDATE assets a
                LEFT JOIN asset_types t ON a.asset_type_id = t.id
                SET a.asset_type_id = 59
                WHERE (t.id IS NOT NULL AND LOWER(t.name) IN ('system','systems')) OR a.asset_type_id = 68
            """)
        else:
            # Normalize text type if only text column exists
            if has_column(cur, 'assets', 'asset_type'):
                cur.execute("""
                    UPDATE assets SET asset_type = 'System'
                    WHERE LOWER(asset_type) IN ('system','systems')
                """)

        # stock mapping (if table exists and column present)
        try:
            cur.execute("SHOW TABLES LIKE 'stock'")
            if cur.fetchone():
                if has_column(cur, 'stock', 'asset_type_id'):
                    cur.execute("""
                        UPDATE stock s
                        JOIN asset_types t ON s.asset_type_id = t.id
                        SET s.asset_type_id = 59
                        WHERE LOWER(t.name) IN ('system','systems') OR s.asset_type_id = 68
                    """)
        except Exception:
            pass

        cur.execute("SET SQL_SAFE_UPDATES=1")
        print('OK: Mapping updated to 59')
    finally:
        cur.close(); conn.close()

if __name__ == '__main__':
    main()
