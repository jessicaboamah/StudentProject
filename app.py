import os
import json
import sqlite3
import hashlib
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash

app = Flask(__name__)
app.secret_key = "super_secret_student_hub_key_123"

# ==========================================
# DATABASE SETUP & UTILITIES
# ==========================================
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    conn = sqlite3.connect("student_hub.db")
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY, password_hash TEXT, profile_json TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            class_name TEXT,
            FOREIGN KEY(username) REFERENCES users(username)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS grades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER,
            assignment_name TEXT,
            score REAL,
            weight REAL,
            due_date TEXT,
            priority TEXT,
            is_complete INTEGER DEFAULT 0,
            FOREIGN KEY(class_id) REFERENCES classes(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS streaks (
            username TEXT PRIMARY KEY, 
            coding_streak INTEGER DEFAULT 0, 
            reading_streak INTEGER DEFAULT 0,
            FOREIGN KEY(username) REFERENCES users(username)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ai_chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            username TEXT, 
            prompt TEXT, 
            response TEXT, 
            timestamp TEXT,
            FOREIGN KEY(username) REFERENCES users(username)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS saved_flashcards (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            username TEXT, 
            front TEXT, 
            back TEXT, 
            timestamp TEXT,
            FOREIGN KEY(username) REFERENCES users(username)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS saved_quizzes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            username TEXT, 
            topic TEXT, 
            quiz_json TEXT, 
            score TEXT, 
            timestamp TEXT,
            FOREIGN KEY(username) REFERENCES users(username)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ai_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            username TEXT, 
            goal_text TEXT, 
            recommendations TEXT, 
            status TEXT DEFAULT 'Active', 
            timestamp TEXT,
            FOREIGN KEY(username) REFERENCES users(username)
        )
    ''')
    
    conn.commit()

    # Create default demo user if it doesn't exist
    cursor.execute("SELECT username FROM users WHERE username = '123'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users VALUES (?, ?, ?)", ("123", hash_password("123"), json.dumps({"role": "Student", "grade_level": "High School", "joined_year": 2026})))
        cursor.execute("INSERT INTO streaks VALUES (?, 0, 0)", ("123",))
        conn.commit()

    conn.close()

init_db()

def calculate_gpa(score):
    if score >= 90: return 4.0
    elif score >= 80: return 3.0
    elif score >= 70: return 2.0
    elif score >= 60: return 1.0
    else: return 0.0

def get_ai_client(user_provided_key=None):
    try:
        from google import genai
        target_key = user_provided_key or session.get('api_key') or os.environ.get("GEMINI_API_KEY") or "AQ.Ab8RN6LvWtsnuMUS31753LAoMu5WXUfHtVnblp4-W9RjIbrhHg"
        return genai.Client(api_key=target_key)
    except Exception:
        return None

# ==========================================
# CORE DASHBOARD ROUTES
# ==========================================
@app.route('/')
def dashboard():
    if "username" not in session:
        return redirect('/login')
        
    username = session["username"]
    conn = sqlite3.connect("student_hub.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT profile_json FROM users WHERE username = ?", (username,))
    user_row = cursor.fetchone()
    profile_data = json.loads(user_row[0]) if user_row and user_row[0] else {"role": "Student", "grade_level": "High School", "joined_year": 2026}
    
    cursor.execute("SELECT coding_streak, reading_streak FROM streaks WHERE username = ?", (username,))
    streak_data = cursor.fetchone() or (0, 0)
    streaks = {"coding": streak_data[0], "reading": streak_data[1]}

    cursor.execute("SELECT id, class_name FROM classes WHERE username = ?", (username,))
    user_classes = cursor.fetchall()
    
    classes_list = []
    all_assignments = []
    total_gpa_points = 0
    total_score_points = 0
    class_count = 0
    graded_class_count = 0
    total_assignments_cnt = 0
    completed_assignments_cnt = 0
    pending_assignments_cnt = 0
    upcoming_assignments = []
    today_str = datetime.today().strftime('%Y-%m-%d')

    for class_id, class_name in user_classes:
        cursor.execute("SELECT id, assignment_name, score, weight, due_date, priority, is_complete FROM grades WHERE class_id = ?", (class_id,))
        assignments = cursor.fetchall()
        
        total_weighted_score = 0
        total_weight = 0
        
        for a_id, a_name, score, weight, due_date, priority, is_complete in assignments:
            total_assignments_cnt += 1
            if is_complete:
                completed_assignments_cnt += 1
            else:
                pending_assignments_cnt += 1
                if due_date and due_date >= today_str:
                    upcoming_assignments.append({"name": a_name, "class_name": class_name, "due_date": due_date, "priority": priority})

            all_assignments.append({
                "id": a_id, "class_id": class_id, "class_name": class_name, "name": a_name,
                "score": score, "weight": weight, "due_date": due_date, "priority": priority, "is_complete": is_complete
            })
            
            if score is not None and score >= 0:
                total_weighted_score += (score * (weight / 100.0))
                total_weight += (weight / 100.0)
        
        if total_weight > 0:
            class_average = min(100.0, total_weighted_score / total_weight)
            graded_class_count += 1
            total_score_points += class_average
        else:
            class_average = 100.0
        
        class_gpa = calculate_gpa(class_average)
        total_gpa_points += class_gpa
        class_count += 1

        classes_list.append({"id": class_id, "name": class_name, "average": round(class_average, 1), "gpa": class_gpa})
    
    upcoming_assignments = sorted(upcoming_assignments, key=lambda x: x['due_date'])[:3]
    overall_gpa = round(total_gpa_points / class_count, 2) if class_count > 0 else 4.0
    overall_average = round(total_score_points / graded_class_count, 1) if graded_class_count > 0 else 100.0

    conn.close()
    
    return render_template(
        "dashboard.html", username=username, profile=profile_data, streaks=streaks, 
        classes=classes_list, assignments=all_assignments, overall_gpa=overall_gpa, overall_average=overall_average,
        total_subjects=class_count, total_assignments=total_assignments_cnt, completed_assignments=completed_assignments_cnt, 
        pending_assignments=pending_assignments_cnt, upcoming=upcoming_assignments
    )

# ==========================================
# ACADEMIC SUBJECT WORKSPACES
# ==========================================
@app.route('/add_class', methods=['POST'])
def add_class():
    if "username" in session:
        class_name = request.form.get('class_name', '').strip()
        if class_name:
            conn = sqlite3.connect("student_hub.db")
            cursor = conn.cursor()
            cursor.execute("INSERT INTO classes (username, class_name) VALUES (?, ?)", (session["username"], class_name))
            conn.commit()
            conn.close()
        return redirect(url_for('dashboard'))
    return redirect('/login')

@app.route('/delete_class/<int:class_id>')
def delete_class(class_id):
    if "username" in session:
        conn = sqlite3.connect("student_hub.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM grades WHERE class_id = ?", (class_id,))
        cursor.execute("DELETE FROM classes WHERE id = ? AND username = ?", (class_id, session["username"]))
        conn.commit()
        conn.close()
    return redirect(url_for('dashboard'))

# ==========================================
# ASSIGNMENT HANDLERS
# ==========================================
@app.route('/add_assignment', methods=['POST'])
def add_assignment():
    if "username" in session:
        class_id = request.form.get('class_id')
        assignment_name = request.form.get('assignment_name', '').strip()
        score_input = request.form.get('score', '').strip()
        weight_input = request.form.get('weight', '').strip()
        due_date = request.form.get('due_date')
        priority = request.form.get('priority')
        
        score = float(score_input) if score_input != "" else -1.0
        weight = float(weight_input) if weight_input else 10.0

        conn = sqlite3.connect("student_hub.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO grades (class_id, assignment_name, score, weight, due_date, priority, is_complete) VALUES (?, ?, ?, ?, ?, ?, 0)", 
            (class_id, assignment_name, score, weight, due_date, priority)
        )
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))
    return redirect('/login')

@app.route('/toggle_complete/<int:assignment_id>')
def toggle_complete(assignment_id):
    if "username" in session:
        conn = sqlite3.connect("student_hub.db")
        cursor = conn.cursor()
        cursor.execute("SELECT is_complete FROM grades WHERE id = ?", (assignment_id,))
        result = cursor.fetchone()
        if result:
            cursor.execute("UPDATE grades SET is_complete = ? WHERE id = ?", (1 if result[0] == 0 else 0, assignment_id))
            conn.commit()
        conn.close()
    return redirect(url_for('dashboard'))

@app.route('/delete_assignment/<int:assignment_id>')
def delete_assignment(assignment_id):
    if "username" in session:
        conn = sqlite3.connect("student_hub.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM grades WHERE id = ?", (assignment_id,))
        conn.commit()
        conn.close()
    return redirect(url_for('dashboard'))

# ==========================================
# STREAKS MANAGER
# ==========================================
@app.route('/increment_streak/<activity>')
def increment_streak(activity):
    if "username" in session and activity in ["coding", "reading"]:
        conn = sqlite3.connect("student_hub.db")
        cursor = conn.cursor()
        cursor.execute(f"UPDATE streaks SET {activity}_streak = {activity}_streak + 1 WHERE username = ?", (session["username"],))
        conn.commit()
        conn.close()
    return redirect(url_for('dashboard'))

@app.route('/reset_streak/<activity>')
def reset_streak(activity):
    if "username" in session and activity in ["coding", "reading"]:
        conn = sqlite3.connect("student_hub.db")
        cursor = conn.cursor()
        cursor.execute(f"UPDATE streaks SET {activity}_streak = 0 WHERE username = ?", (session["username"],))
        conn.commit()
        conn.close()
    return redirect(url_for('dashboard'))

# ==========================================
# AUTHENTICATION HUB
# ==========================================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')
        if username and password:
            conn = sqlite3.connect("student_hub.db")
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT INTO users VALUES (?, ?, ?)", (username, hash_password(password), json.dumps({"role": "Student", "grade_level": "High School", "joined_year": 2026})))
                cursor.execute("INSERT INTO streaks VALUES (?, 0, 0)", (username,))
                conn.commit()
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("Username already taken!")
            finally:
                conn.close()
    return render_template("register.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')
        conn = sqlite3.connect("student_hub.db")
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
        result = cursor.fetchone()
        conn.close()
        if result and result[0] == hash_password(password):
            session["username"] = username  
            return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route('/logout')
def logout():
    session.pop("username", None) 
    return redirect('/login')

# ==========================================
# AI SUITE & HUB TOOLS 
# ==========================================
@app.route('/ai_suite')
def ai_suite():
    if "username" not in session:
        return redirect('/login')
    return render_template("ai_suite.html", current_key=session.get('api_key', ''))

@app.route('/ai/save_key', methods=['POST'])
def save_key():
    key = request.form.get('api_key', '').strip()
    if key: session['api_key'] = key
    else: session.pop('api_key', None)
    return redirect(url_for('ai_suite'))

@app.route('/ai/homework_helper', methods=['POST'])
def ai_homework_helper():
    if "username" not in session: return {"error": "Unauthorized"}, 401
    ai_client = get_ai_client()
    if not ai_client: return {"error": "API Key initialization failed."}, 500
    
    data = request.json or {}
    text = data.get('text', '').strip()
    mode = data.get('mode', 'explain')
    prompt = f"Explain this: {text}" if mode == "explain" else f"Summarize this: {text}"
    
    try:
        response = ai_client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        return {"result": response.text}
    except Exception as e:
        return {"error": str(e)}, 500

@app.route('/ai/generate_notes', methods=['POST'])
def ai_generate_notes():
    if "username" not in session: return {"error": "Unauthorized"}, 401
    ai_client = get_ai_client()
    if not ai_client: return {"error": "API Key initialization failed."}, 500
    
    topic = (request.json or {}).get('topic', '').strip()
    try:
        response = ai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=f"Create a clean study guide notes summary for: {topic}"
        )
        return {"notes": response.text}
    except Exception as e:
        return {"error": str(e)}, 500

# 🌟 UPDATED: Accepting standard form text to fix the 415 error!
@app.route('/ai/goal_coach', methods=['POST'])
def ai_goal_coach():
    if "username" not in session: 
        return redirect('/login')
        
    ai_client = get_ai_client()
    if not ai_client: 
        return "API Key initialization failed.", 500
    
    # Check both JSON data or normal HTML text input data
    if request.is_json:
        data = request.json or {}
        goal_text = data.get('goal', '').strip()
    else:
        goal_text = request.form.get('goal', '').strip()
        
    if not goal_text: 
        return "Goal description cannot be empty.", 400
    
    prompt = f"Act as an expert academic coach. Provide a bulleted, highly motivational 3-step action plan to achieve this student goal: '{goal_text}'"
    try:
        response = ai_client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        return {"result": response.text}
    except Exception as e:
        return str(e), 500

@app.route('/ai/download_notes')
def download_notes():
    if "username" not in session: return redirect('/login')
    topic = request.args.get('topic', 'Notes')
    content = request.args.get('content', '')
    return f"<html><body onload='window.print()'><h2>{topic}</h2><pre>{content}</pre></body></html>"

if __name__ == '__main__':
    app.run(debug=True)
