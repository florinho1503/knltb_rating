import sqlite3

def remove_duplicates(db_path: str, table: str):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 1) Create a temporary table of the unique rows by keeping the lowest ROWID per group
    cur.execute(f"""
        CREATE TEMPORARY TABLE keep AS
        SELECT MIN(rowid) AS keep_id
        FROM {table}
        GROUP BY player1, player2, rating1, rating2
    """)

    # 2) Delete all rows whose rowid is NOT in the keep list
    cur.execute(f"""
        DELETE FROM {table}
        WHERE rowid NOT IN (SELECT keep_id FROM keep)
    """)

    # 3) Drop the temp table and commit
    cur.execute("DROP TABLE keep;")
    conn.commit()
    conn.close()
    print(f"Duplicates removed from `{table}` in `{db_path}`.")

if __name__ == "__main__":
    remove_duplicates("matches.db", "matches")
