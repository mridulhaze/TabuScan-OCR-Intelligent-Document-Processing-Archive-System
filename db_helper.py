import pyodbc

CONN_STR = (
    r"Driver={ODBC Driver 17 for SQL Server};"
    r"Server=localhost\SQLEXPRESS;"
    r"Database=tabulation;"
    r"Trusted_Connection=yes;"
    r"MultipleActiveResultSets=true;"
)

def connect_db():
    return pyodbc.connect(CONN_STR)

def create_report_table_if_not_exists():
    conn = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT OBJECT_ID(N'dbo.scan_report', N'U')")
        table_id = cursor.fetchone()[0]
        if table_id is None:
            print("Creating database table dbo.scan_report...")
            cursor.execute("""
                CREATE TABLE dbo.scan_report (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    tabulation VARCHAR(255) NOT NULL,
                    exm_name VARCHAR(255) NULL,
                    exm_year VARCHAR(255) NULL,
                    rows_count INT NULL,
                    scan_time REAL NULL,
                    upload_time REAL NULL,
                    upload_date DATETIME DEFAULT GETDATE()
                )
            """)
            conn.commit()
    finally:
        cursor.close()
        conn.close()

def check_table_exists():
    try:
        create_report_table_if_not_exists()
    except Exception as e:
        print(f"Error creating scan_report table: {e}")
        
    try:
        conn = connect_db()
        cursor = conn.cursor()
        
        # Check if tabu table exists
        cursor.execute("SELECT OBJECT_ID(N'dbo.tabu', N'U')")
        tabu_exists = cursor.fetchone()[0] is not None
        
        # Check if tabu table has the old schema (contains 'image' column)
        has_old_schema = False
        if tabu_exists:
            cursor.execute("SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'tabu' AND COLUMN_NAME = 'image'")
            has_old_schema = cursor.fetchone() is not None
            
        if has_old_schema:
            print("Upgrading database schema to normalized master-detail structure...")
            try:
                cursor.execute("DROP TABLE dbo.tabu")
                conn.commit()
                tabu_exists = False
            except Exception as de:
                print(f"Error dropping old tabu table: {de}")
                conn.rollback()

        # Create tabu_sheet master table if not exists
        cursor.execute("SELECT OBJECT_ID(N'dbo.tabu_sheet', N'U')")
        sheet_exists = cursor.fetchone()[0] is not None
        if not sheet_exists:
            print("Creating database table dbo.tabu_sheet...")
            cursor.execute("""
                CREATE TABLE dbo.tabu_sheet (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    tabulation VARCHAR(255) NOT NULL,
                    exm_name VARCHAR(255) NULL,
                    exm_year VARCHAR(255) NULL,
                    image VARBINARY(MAX) NULL
                )
            """)
            cursor.execute("CREATE UNIQUE INDEX idx_tabu_sheet_uniq ON dbo.tabu_sheet(tabulation, exm_name, exm_year)")
            conn.commit()
            
        # Create tabu detail table if not exists
        if not tabu_exists:
            print("Creating database table dbo.tabu...")
            cursor.execute("""
                CREATE TABLE dbo.tabu (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    sheet_id INT NOT NULL FOREIGN KEY REFERENCES dbo.tabu_sheet(id) ON DELETE CASCADE,
                    exm_name VARCHAR(255) NOT NULL,
                    exm_year VARCHAR(255) NOT NULL,
                    exm_roll VARCHAR(255) NOT NULL,
                    rege_no INT NULL,
                    tabulation VARCHAR(255) NOT NULL
                )
            """)
            conn.commit()
            
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Error checking/creating tables: {e}")
        return False

def insert_scan_report(tabulation, exm_name, exm_year, rows_count, scan_time, upload_time):
    conn = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO dbo.scan_report (tabulation, exm_name, exm_year, rows_count, scan_time, upload_time) VALUES (?, ?, ?, ?, ?, ?)",
            (tabulation, exm_name, exm_year, rows_count, scan_time, upload_time)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()

def get_scan_reports():
    conn = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT tabulation, exm_name, exm_year, rows_count, scan_time, upload_time, upload_date FROM dbo.scan_report ORDER BY upload_date DESC")
        columns = [column[0] for column in cursor.description]
        records = []
        for row in cursor.fetchall():
            record = dict(zip(columns, row))
            if record.get("upload_date"):
                record["upload_date"] = record["upload_date"].strftime("%Y-%m-%d %H:%M:%S")
            records.append(record)
        return records
    finally:
        cursor.close()
        conn.close()

def get_or_create_tabu_sheet(tabulation, exm_name, exm_year, image_bytes=None):
    conn = connect_db()
    cursor = conn.cursor()
    try:
        # Check if sheet already exists, and whether it has an image binary stored
        cursor.execute(
            "SELECT id, CASE WHEN image IS NULL THEN 0 ELSE 1 END FROM dbo.tabu_sheet WHERE tabulation = ? AND exm_name = ? AND exm_year = ?",
            (tabulation, exm_name, exm_year)
        )
        row = cursor.fetchone()
        if row:
            sheet_id = row[0]
            has_image = row[1] == 1
            # If we need to store the image and it's not present, write it now
            if not has_image and image_bytes is not None:
                cursor.execute(
                    "UPDATE dbo.tabu_sheet SET image = ? WHERE id = ?",
                    (pyodbc.Binary(image_bytes), sheet_id)
                )
                conn.commit()
            return sheet_id
        else:
            # Create new sheet record
            binary_img = pyodbc.Binary(image_bytes) if image_bytes is not None else None
            cursor.execute(
                "INSERT INTO dbo.tabu_sheet (tabulation, exm_name, exm_year, image) VALUES (?, ?, ?, ?)",
                (tabulation, exm_name, exm_year, binary_img)
            )
            conn.commit()
            
            # Fetch the generated identity ID
            cursor.execute("SELECT @@IDENTITY")
            sheet_id = int(cursor.fetchone()[0])
            return sheet_id
    finally:
        cursor.close()
        conn.close()

def insert_tabu_record(exm_name, exm_year, exm_roll, rege_no, tabulation, image_bytes=None):
    # Resolve or create the master sheet first
    sheet_id = get_or_create_tabu_sheet(tabulation, exm_name, exm_year, image_bytes)
    
    conn = connect_db()
    cursor = conn.cursor()
    try:
        # Check if combination of exm_name, exm_year, exm_roll already exists in detail table
        cursor.execute(
            "SELECT COUNT(*) FROM dbo.tabu WHERE exm_name = ? AND exm_year = ? AND exm_roll = ?",
            (exm_name, exm_year, exm_roll)
        )
        exists = cursor.fetchone()[0] > 0
        
        if exists:
            # Update the registration number and tabulation path
            cursor.execute(
                "UPDATE dbo.tabu SET rege_no = ?, tabulation = ?, sheet_id = ? WHERE exm_name = ? AND exm_year = ? AND exm_roll = ?",
                (rege_no, tabulation, sheet_id, exm_name, exm_year, exm_roll)
            )
            action = "UPDATED"
        else:
            # Insert new detail student record linked to master sheet_id
            cursor.execute(
                "INSERT INTO dbo.tabu (sheet_id, exm_name, exm_year, exm_roll, rege_no, tabulation) VALUES (?, ?, ?, ?, ?, ?)",
                (sheet_id, exm_name, exm_year, exm_roll, rege_no, tabulation)
            )
            action = "INSERTED"
            
        conn.commit()
        return action
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()

def get_tabu_image(exm_roll=None, rege_no=None, exm_year=None, tabulation=None):
    conn = connect_db()
    cursor = conn.cursor()
    try:
        # Query image from master table using detail matches
        query = "SELECT s.image FROM dbo.tabu_sheet s INNER JOIN dbo.tabu t ON t.sheet_id = s.id WHERE 1=1"
        params = []
        if exm_roll:
            query += " AND t.exm_roll = ?"
            params.append(exm_roll)
        if rege_no is not None:
            query += " AND t.rege_no = ?"
            params.append(rege_no)
        if exm_year:
            query += " AND t.exm_year = ?"
            params.append(exm_year)
        if tabulation:
            query += " AND t.tabulation = ?"
            params.append(tabulation)
            
        cursor.execute(query, params)
        row = cursor.fetchone()
        if row and row[0]:
            return row[0]
            
        # Fallback: direct sheet lookup by tabulation filename
        if tabulation:
            cursor.execute("SELECT image FROM dbo.tabu_sheet WHERE tabulation = ?", (tabulation,))
            row = cursor.fetchone()
            if row and row[0]:
                return row[0]
                
        return None
    finally:
        cursor.close()
        conn.close()

def get_tabu_records():
    conn = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT exm_name, exm_year, exm_roll, rege_no, tabulation FROM dbo.tabu ORDER BY exm_name, exm_year, exm_roll")
        columns = [column[0] for column in cursor.description]
        records = []
        for row in cursor.fetchall():
            records.append(dict(zip(columns, row)))
        return records
    finally:
        cursor.close()
        conn.close()

def clear_tabu_table():
    conn = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM dbo.tabu")
        cursor.execute("DELETE FROM dbo.tabu_sheet")
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()

def validate_user_login(username, password):
    conn = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT [name], [user], [position] FROM dbo.[USER] WHERE [user] = ? AND [pass] = ? AND [expire] = 'N' AND [status] = 'Y'",
            (username, password)
        )
        row = cursor.fetchone()
        if row:
            return {
                "name": row[0],
                "username": row[1],
                "position": row[2]
            }
        return None
    finally:
        cursor.close()
        conn.close()

def get_all_users():
    conn = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT [id], [name], [user], [pass], [expire], [status], [position] FROM dbo.[USER] ORDER BY [id]")
        columns = [column[0] for column in cursor.description]
        records = []
        for row in cursor.fetchall():
            records.append(dict(zip(columns, row)))
        return records
    finally:
        cursor.close()
        conn.close()

def create_user(name, username, password, expire, status, position):
    conn = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT ISNULL(MAX([id]), 0) FROM dbo.[USER]")
        max_id = cursor.fetchone()[0]
        new_id = max_id + 1
        
        cursor.execute(
            "INSERT INTO dbo.[USER] ([id], [name], [user], [pass], [expire], [status], [position]) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (new_id, name, username, password, expire, status, position)
        )
        conn.commit()
        return new_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()

def update_user(user_id, name, password, expire, status, position):
    conn = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE dbo.[USER] SET [name] = ?, [pass] = ?, [expire] = ?, [status] = ?, [position] = ? WHERE [id] = ?",
            (name, password, expire, status, position, user_id)
        )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()

def delete_user(user_id):
    conn = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM dbo.[USER] WHERE [id] = ?", (user_id,))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()
