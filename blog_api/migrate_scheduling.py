import sqlite3

DB_PATH = "blog.db"


def column_exists(cur, table, column):
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

if not column_exists(cur, "posts", "status"):
    cur.execute("ALTER TABLE posts ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'published'")
if not column_exists(cur, "posts", "scheduled_at"):
    cur.execute("ALTER TABLE posts ADD COLUMN scheduled_at DATETIME")
if not column_exists(cur, "posts", "published_at"):
    cur.execute("ALTER TABLE posts ADD COLUMN published_at DATETIME")
    cur.execute("UPDATE posts SET published_at = created_at WHERE published_at IS NULL")

conn.commit()
conn.close()
print("Migration complete.")