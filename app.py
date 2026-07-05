from flask import Flask, jsonify, request, send_from_directory, session
import os
import threading
from db_helper import insert_tabu_record, get_tabu_records, clear_tabu_table, check_table_exists, validate_user_login, insert_scan_report, get_scan_reports
from ocr_core import process_tabulation_image
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
app = Flask(__name__)
app.secret_key = "tabuscan_secret_key_12345"
ROOT_DIR = r"E:\projects\antigravity\archive_momin"

# In-memory status for long-running operations if needed, but since we do image-by-image OCR, 
# we can run it synchronously or with quick API calls.
ocr_status = {
    "status": "idle",
    "progress": 0,
    "current_file": "",
    "error": None
}

@app.route("/")
def index():
    # Clear the server session on page load/refresh (force logout)
    session.pop("user_info", None)
    
    # Serve index.html with cache-disabling headers to force browser reload state
    from flask import make_response
    response = make_response(send_from_directory("templates", "index.html"))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route("/static/<path:path>")
def send_static(path):
    return send_from_directory("static", path)

@app.route('/images/<path:filename>')
def serve_image(filename):
    # Safe directory serving of files under root archive folder
    return send_from_directory(ROOT_DIR, filename)

@app.route("/api/scan-archive", methods=["GET"])
def scan_archive():
    """Scans the archive folder recursively and returns list of images with exm_name and exm_year"""
    images = []
    
    # We will get all records already in DB to show which images are already processed
    db_records = []
    try:
        db_records = get_tabu_records()
    except Exception as e:
        print(f"Error fetching DB records during scan: {e}")
        
    processed_images = set(r["tabulation"] for r in db_records)
    
    for root, dirs, files in os.walk(ROOT_DIR):
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                full_path = os.path.join(root, file)
                # Get path relative to ROOT_DIR
                rel_path = os.path.relpath(full_path, ROOT_DIR)
                parts = rel_path.split(os.sep)
                
                # Determine exm_name and exm_year from the path dynamically
                exm_name = None
                exm_year = None
                tabulation = parts[-1]
                
                if len(parts) >= 3:
                    exm_name = parts[0]
                    exm_year = parts[1]
                elif len(parts) == 2:
                    exm_name = os.path.basename(ROOT_DIR.rstrip('/\\'))
                    exm_year = parts[0]
                elif len(parts) == 1:
                    # Try to extract year from ROOT_DIR path
                    import re
                    year_match = re.search(r'\b(19\d{2}|20\d{2})\b', ROOT_DIR)
                    if year_match:
                        exm_year = year_match.group(1)
                        parent_dir = os.path.dirname(ROOT_DIR.rstrip('/\\'))
                        exm_name = os.path.basename(parent_dir)
                        if not exm_name:
                            exm_name = os.path.basename(ROOT_DIR.rstrip('/\\'))
                    else:
                        exm_name = os.path.basename(ROOT_DIR.rstrip('/\\'))
                        exm_year = "Default"
                else:
                    continue
                
                if not exm_name:
                    exm_name = "DefaultExam"
                if not exm_year:
                    exm_year = "Default"
                
                images.append({
                    "rel_path": rel_path.replace(os.sep, '/'),
                    "exm_name": exm_name,
                    "exm_year": exm_year,
                    "filename": tabulation,
                    "processed": tabulation in processed_images
                })
                    
    return jsonify({
        "success": True,
        "images": images,
        "db_connected": check_table_exists()
    })

@app.route("/api/set-archive-folder", methods=["POST"])
def set_archive_folder():
    global ROOT_DIR
    data = request.json
    if not data or "folder_path" not in data:
        return jsonify({"success": False, "error": "Missing folder_path"}), 400
        
    folder_path = data["folder_path"].strip()
    if not os.path.exists(folder_path):
        return jsonify({"success": False, "error": f"Folder path does not exist: {folder_path}"}), 400
        
    ROOT_DIR = folder_path
    print(f"Archive folder path updated to: {ROOT_DIR}")
    return jsonify({
        "success": True,
        "message": f"Archive folder updated to: {ROOT_DIR}"
    })

@app.route("/api/select-folder-dialog", methods=["GET"])
def select_folder_dialog():
    """Opens a native OS folder dialog using a subprocess to avoid Tkinter threading errors"""
    import subprocess
    import sys
    
    code = (
        "import tkinter as tk; "
        "from tkinter import filedialog; "
        "root=tk.Tk(); "
        "root.withdraw(); "
        "root.attributes('-topmost', True); "
        "print(filedialog.askdirectory(title='Select Tabulation Archive Folder'))"
    )
    
    try:
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            
        res = subprocess.run(
            ["python", "-c", code],
            capture_output=True,
            text=True,
            startupinfo=startupinfo,
            timeout=180
        )
        
        folder_selected = res.stdout.strip()
        if folder_selected:
            # Normalize for current OS
            folder_selected = os.path.abspath(folder_selected)
            return jsonify({
                "success": True, 
                "folder_path": folder_selected.replace(os.sep, '/')
            })
        else:
            return jsonify({"success": False, "error": "Folder selection was cancelled."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/run-ocr", methods=["POST"])
def run_ocr():
    """Runs OCR on a specific image and returns clustered rows for verification"""
    data = request.json
    if not data or "rel_path" not in data:
        return jsonify({"success": False, "error": "Missing rel_path"}), 400
        
    rel_path = data["rel_path"].replace('/', os.sep)
    full_path = os.path.join(ROOT_DIR, rel_path)
    
    try:
        parsed_rows = process_tabulation_image(full_path)
        return jsonify({
            "success": True,
            "rows": parsed_rows
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/save-records", methods=["POST"])
def save_records():
    """Saves the verified OCR results to the database, including the binary image data"""
    data = request.json
    if not data or "records" not in data:
        return jsonify({"success": False, "error": "Missing records data"}), 400
        
    records = data["records"]
    scan_time = data.get("scan_time")
    upload_time = data.get("upload_time")
    
    results = []
    image_cache = {}
    
    try:
        for r in records:
            # Prepare rege_no (convert to int or None)
            reg_val = r.get("rege_no")
            if reg_val is not None and str(reg_val).strip() != "":
                try:
                    reg_val = int(float(str(reg_val).strip()))
                except ValueError:
                    reg_val = None
            else:
                reg_val = None
                    
            # Load and cache image binary data to save in VARBINARY column
            tab_file = r.get("tabulation")
            ex_name = r.get("exm_name")
            ex_year = r.get("exm_year")
            cache_key = f"{ex_name}/{ex_year}/{tab_file}"
            
            img_bytes = None
            if cache_key not in image_cache:
                # Try finding the file using candidate path structures:
                # 1. ROOT_DIR / ex_name / ex_year / tab_file (when ROOT_DIR is parent of ex_name)
                # 2. ROOT_DIR / ex_year / tab_file (when ROOT_DIR is ex_name itself)
                # 3. ROOT_DIR / tab_file (when images are directly in ROOT_DIR)
                candidate_paths = [
                    os.path.join(ROOT_DIR, ex_name, ex_year, tab_file),
                    os.path.join(ROOT_DIR, ex_year, tab_file),
                    os.path.join(ROOT_DIR, tab_file)
                ]
                
                img_path = None
                for path in candidate_paths:
                    if os.path.exists(path):
                        img_path = path
                        break
                
                # If not found in primary candidates, search recursively in ROOT_DIR
                if not img_path:
                    all_matches = []
                    for root_dir, _, filenames in os.walk(ROOT_DIR):
                        if tab_file in filenames:
                            all_matches.append(os.path.join(root_dir, tab_file))
                    
                    if len(all_matches) == 1:
                        img_path = all_matches[0]
                    elif len(all_matches) > 1:
                        # Find the one that matches ex_year in its path segment
                        for match in all_matches:
                            norm_match = match.replace('\\', '/')
                            path_segments = norm_match.split('/')
                            if ex_year in path_segments:
                                img_path = match
                                break
                        # Fallback to the first match if year check did not hit
                        if not img_path:
                            img_path = all_matches[0]
                
                if img_path:
                    print(f"Reading binary image bytes for database upload: {img_path}")
                    with open(img_path, "rb") as f:
                        image_cache[cache_key] = f.read()
                else:
                    print(f"Warning: Image file not found for cache key {cache_key} in {ROOT_DIR}")
                    image_cache[cache_key] = None
                img_bytes = image_cache.get(cache_key)
            
            action = insert_tabu_record(
                exm_name=ex_name,
                exm_year=ex_year,
                exm_roll=str(r.get("exm_roll", "")).strip(),
                rege_no=reg_val,
                tabulation=tab_file,
                image_bytes=img_bytes
            )
            results.append({
                "exm_roll": r.get("exm_roll"),
                "action": action
            })
            
        # Insert a scan report if records were saved successfully
        if records:
            first_rec = records[0]
            tabulation = first_rec.get("tabulation")
            ex_name = first_rec.get("exm_name")
            ex_year = first_rec.get("exm_year")
            
            try:
                insert_scan_report(
                    tabulation=tabulation,
                    exm_name=ex_name,
                    exm_year=ex_year,
                    rows_count=len(records),
                    scan_time=scan_time,
                    upload_time=upload_time
                )
            except Exception as re:
                print(f"Error inserting scan report: {re}")
            
        return jsonify({
            "success": True,
            "saved_count": len(records),
            "details": results
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/search-tabulation", methods=["GET"])
def search_tabulation():
    """Searches the database for a student image by roll, registration, or tabulation filename"""
    roll = request.args.get("roll")
    reg = request.args.get("reg")
    year = request.args.get("year")
    tabulation = request.args.get("tabulation")
    
    if not roll and not reg and not tabulation:
        return jsonify({"success": False, "error": "Please provide a search criteria (roll, registration, or tabulation)"}), 400
        
    try:
        reg_int = int(reg) if reg else None
    except ValueError:
        reg_int = None
        
    from db_helper import get_tabu_image
    img_bytes = get_tabu_image(exm_roll=roll, rege_no=reg_int, exm_year=year, tabulation=tabulation)
    
    if img_bytes:
        from flask import Response
        return Response(img_bytes, mimetype="image/jpeg")
    else:
        return jsonify({"success": False, "error": "No tabulation sheet image found in database for this query"}), 404

@app.route("/api/db-records", methods=["GET"])
def db_records():
    """Gets all current records in the database"""
    try:
        records = get_tabu_records()
        return jsonify({
            "success": True,
            "records": records
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/scan-reports", methods=["GET"])
def api_scan_reports():
    """Gets all scanning/uploading reports"""
    try:
        reports = get_scan_reports()
        return jsonify({
            "success": True,
            "reports": reports
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/clear-db", methods=["POST"])
def clear_db():
    """Clears the tabulation table. Restricted to AP (Admin Partner) position only."""
    user_info = session.get("user_info")
    if not user_info or user_info.get("position") != "AP":
        return jsonify({"success": False, "error": "Access Denied: Only users with AP position can clear the database table."}), 403
        
    try:
        clear_tabu_table()
        return jsonify({
            "success": True,
            "message": "Database table tabu cleared successfully."
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/export-csv", methods=["GET"])
def export_csv():
    """Generates and downloads a CSV export of all database records"""
    try:
        records = get_tabu_records()
        
        import csv
        import io
        from flask import Response
        
        si = io.StringIO()
        cw = csv.writer(si)
        
        # Write headers
        cw.writerow(["Exam Name", "Exam Year", "Roll Number", "Registration Number", "Tabulation Sheet Path"])
        
        # Write data
        for r in records:
            cw.writerow([
                r.get("exm_name", ""),
                r.get("exm_year", ""),
                r.get("exm_roll", ""),
                r.get("rege_no", "") or "",
                r.get("tabulation", "")
            ])
            
        output = si.getvalue()
        return Response(
            output,
            mimetype="text/csv",
            headers={"Content-disposition": "attachment; filename=tabulation_records.csv"}
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/search-tabulations-batch", methods=["GET"])
def search_tabulations_batch():
    """Searches and groups tabulation sheets by exam name or exam year for batch view"""
    name = request.args.get("name")
    year = request.args.get("year")
    
    if not name and not year:
        return jsonify({"success": False, "error": "Please provide an exam name or exam year to run a batch search."}), 400
        
    from db_helper import connect_db
    conn = connect_db()
    cursor = conn.cursor()
    try:
        query = "SELECT DISTINCT exm_name, exm_year, tabulation FROM dbo.tabu WHERE 1=1"
        params = []
        if name:
            query += " AND exm_name = ?"
            params.append(name)
        if year:
            query += " AND exm_year = ?"
            params.append(year)
            
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        results = []
        for r in rows:
            results.append({
                "exm_name": r[0],
                "exm_year": r[1],
                "tabulation": r[2]
            })
            
        return jsonify({
            "success": True,
            "results": results
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
    finally:
        cursor.close()
        conn.close()

@app.route("/api/login", methods=["POST"])
def login():
    """Validates user login credentials from USER database table"""
    data = request.json
    if not data or "username" not in data or "password" not in data:
        return jsonify({"success": False, "error": "Missing username or password"}), 400
        
    username = data["username"].strip()
    password = data["password"].strip()
    
    user_info = validate_user_login(username, password)
    if user_info:
        session["user_info"] = user_info
        return jsonify({"success": True, "user_info": user_info})
    else:
        return jsonify({"success": False, "error": "Invalid username, password, or account inactive/expired."}), 401

@app.route("/api/logout", methods=["POST"])
def logout():
    """Clears the session on logout"""
    session.pop("user_info", None)
    return jsonify({"success": True, "message": "Logged out successfully."})

@app.route("/api/user-info", methods=["GET"])
def user_info():
    """Returns active user session info"""
    return jsonify({
        "success": True,
        "user_info": session.get("user_info")
    })

def is_admin():
    user_info = session.get("user_info")
    return user_info and user_info.get("position") == "AP"

@app.route("/api/admin/users", methods=["GET"])
def admin_users():
    """Gets all users for the admin panel (restricted to AP position)"""
    if not is_admin():
        return jsonify({"success": False, "error": "Access Denied: Only Admin (AP) can view user records."}), 403
    try:
        from db_helper import get_all_users
        users = get_all_users()
        return jsonify({"success": True, "users": users})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/admin/users", methods=["POST"])
def admin_create_user():
    """Creates a new user (restricted to AP position)"""
    if not is_admin():
        return jsonify({"success": False, "error": "Access Denied: Only Admin (AP) can create users."}), 403
    data = request.json
    if not data or not data.get("user") or not data.get("pass") or not data.get("name"):
        return jsonify({"success": False, "error": "Missing required fields (username, password, or name)"}), 400
    try:
        from db_helper import create_user
        new_id = create_user(
            name=data.get("name"),
            username=data.get("user"),
            password=data.get("pass"),
            expire=data.get("expire", "N"),
            status=data.get("status", "Y"),
            position=data.get("position", "USER")
        )
        return jsonify({"success": True, "id": new_id, "message": "User created successfully."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/admin/users/<int:user_id>", methods=["PUT"])
def admin_update_user(user_id):
    """Updates user password, status, expire, position, or name (restricted to AP position)"""
    if not is_admin():
        return jsonify({"success": False, "error": "Access Denied: Only Admin (AP) can update users."}), 403
    data = request.json
    if not data or not data.get("pass") or not data.get("name"):
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    try:
        from db_helper import update_user
        update_user(
            user_id=user_id,
            name=data.get("name"),
            password=data.get("pass"),
            expire=data.get("expire", "N"),
            status=data.get("status", "Y"),
            position=data.get("position", "USER")
        )
        return jsonify({"success": True, "message": "User updated successfully."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
def admin_delete_user(user_id):
    """Deletes a user from USER table (restricted to AP position)"""
    if not is_admin():
        return jsonify({"success": False, "error": "Access Denied: Only Admin (AP) can delete users."}), 403
    try:
        from db_helper import delete_user
        delete_user(user_id)
        return jsonify({"success": True, "message": "User deleted successfully."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

def get_local_ip():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = '127.0.0.1'
    finally:
        s.close()
    return ip

if __name__ == "__main__":
    # Create templates and static directories if they don't exist
    os.makedirs("templates", exist_ok=True)
    os.makedirs("static", exist_ok=True)
    
    local_ip = get_local_ip()
    print(f"Starting Flask application on http://{local_ip}:5000 and http://127.0.0.1:5000")
    app.run(debug=False, host="0.0.0.0", port=5000)
