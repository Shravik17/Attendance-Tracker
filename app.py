from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
import calendar
import io
import csv
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# =================== Persistent "Database" using CSV ========================

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
STUDENTS_FILE = os.path.join(DATA_DIR, "students.csv")
ATTENDANCE_FILE = os.path.join(DATA_DIR, "attendance.csv")

def ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    # Ensure files exist, create with header if missing
    if not os.path.exists(STUDENTS_FILE):
        with open(STUDENTS_FILE, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'name'])
    if not os.path.exists(ATTENDANCE_FILE):
        with open(ATTENDANCE_FILE, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['date', 'student_id', 'present'])

def load_students():
    lst = []
    max_id = 0
    if os.path.exists(STUDENTS_FILE):
        with open(STUDENTS_FILE, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    sid = int(row['id'])
                    name = row['name']
                    lst.append({"id": sid, "name": name})
                    if sid > max_id: max_id = sid
                except Exception:
                    continue
    return lst, max_id+1 if max_id else 1

def save_students(students):
    with open(STUDENTS_FILE, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['id', 'name'])
        for s in students:
            writer.writerow([s["id"], s["name"]])

def load_attendance():
    att = {}
    if os.path.exists(ATTENDANCE_FILE):
        with open(ATTENDANCE_FILE, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                day = row['date']
                try:
                    sid = int(row['student_id'])
                    present = int(row['present'])
                except Exception:
                    continue
                if day not in att:
                    att[day] = {}
                att[day][sid] = present
    return att

def save_attendance(attendance):
    with open(ATTENDANCE_FILE, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['date', 'student_id', 'present'])
        for d, student_map in attendance.items():
            for sid, pres in student_map.items():
                writer.writerow([d, sid, pres])

# Guarantee data folder and files exist and load data at startup
ensure_data_dir()
students, next_student_id = load_students()
attendance = load_attendance()

# ------------------- In-memory "Database" ----------------------

users = {
    "admin": {
        "id": 1,
        "username": "admin",
        "password_hash": generate_password_hash("admin123"),
        "role": "admin"
    },
    "faculty": {
        "id": 2,
        "username": "faculty",
        "password_hash": generate_password_hash("faculty123"),
        "role": "faculty"
    }
}
next_user_id = 3

# ------------------- Utility Functions ----------------------

def get_all_students():
    return [(student["id"], student["name"]) for student in students]

def get_attendance_for_day(thedate):
    return attendance.get(thedate, {}).copy()

def get_attendance_percentages():
    percentages = []
    all_students = get_all_students()
    stats = {}
    for student_id, _ in all_students:
        stats[student_id] = {"present": 0, "total": 0}
    for date_val in attendance.values():
        for sid, present in date_val.items():
            if sid in stats:
                stats[sid]["total"] += 1
                if present:
                    stats[sid]["present"] += 1
    for sid, name in all_students:
        total = stats[sid]["total"]
        present_count = stats[sid]["present"]
        percent = f'{(present_count / total * 100):.1f}%' if total > 0 else 'N/A'
        percentages.append({"name": name, "present": present_count, "total": total, "percent": percent})
    return percentages

def find_user_by_username(username):
    return users.get(username)

# ------------------- Routes ----------------------

@app.route('/home')
def home():
    return render_template('home.html')

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = find_user_by_username(username)
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('faculty_dashboard'))
        else:
            flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/faculty', methods=['GET', 'POST'])
def faculty_dashboard():
    global attendance
    if 'role' not in session or session['role'] != 'faculty':
        return redirect(url_for('login'))

    all_dates = sorted(attendance.keys())
    if request.method == 'POST':
        selected_date = request.form.get('selected_date', '').strip()
        if not selected_date:
            selected_date = datetime.now().strftime('%Y-%m-%d')
    else:
        selected_date = request.args.get('selected_date', '').strip()
        if not selected_date:
            selected_date = datetime.now().strftime('%Y-%m-%d')

    students_list = get_all_students()
    attendance_map = get_attendance_for_day(selected_date)

    disable_checkbox = False
    today_str = datetime.now().strftime('%Y-%m-%d')
    if selected_date != today_str:
        disable_checkbox = True

    if request.method == 'POST' and not disable_checkbox:
        new_attendance = {}
        for sid, sname in students_list:
            present = 1 if request.form.get(f'present_{sid}') == 'on' else 0
            new_attendance[sid] = present
        attendance[selected_date] = new_attendance
        save_attendance(attendance) # Write to file whenever submitted!
        attendance_map = get_attendance_for_day(selected_date)
        all_dates = sorted(attendance.keys())

    percentages = get_attendance_percentages()
    return render_template('faculty_dashboard.html',
                           students=students_list,
                           attendance_map=attendance_map,
                           selected_date=selected_date,
                           percentages=percentages,
                           all_dates=all_dates,
                           disable_checkbox=disable_checkbox)

@app.route('/faculty/export', methods=['GET'])
def export_attendance():
    if 'role' not in session or session['role'] != 'faculty':
        return redirect(url_for('login'))

    dates_present = sorted(attendance.keys())
    if dates_present:
        default_from = dates_present[0]
        default_to = dates_present[-1]
    else:
        today_str = datetime.now().strftime('%Y-%m-%d')
        default_from = today_str
        default_to = today_str
    students_list = get_all_students()
    return render_template('export_filter.html',
                           students=students_list,
                           default_from=default_from,
                           default_to=default_to)

@app.route('/faculty/export_csv', methods=['POST'])
def export_attendance_csv():
    if 'role' not in session or session['role'] != 'faculty':
        return redirect(url_for('login'))

    from_date = request.form.get('from_date', '').strip()
    to_date = request.form.get('to_date', '').strip()
    try:
        from_date_obj = datetime.strptime(from_date, "%Y-%m-%d").date() if from_date else None
        to_date_obj = datetime.strptime(to_date, "%Y-%m-%d").date() if to_date else None
    except Exception:
        flash('Invalid date selection.')
        return redirect(url_for('export_attendance'))
    
    selected_student_ids = request.form.getlist('student_ids')
    selected_student_ids = set(int(sid) for sid in selected_student_ids if sid.isdigit())

    all_dates = sorted(attendance.keys())
    all_dates_objs = []
    for d in all_dates:
        try:
            all_dates_objs.append(datetime.strptime(d, "%Y-%m-%d").date())
        except Exception:
            continue
    
    if from_date_obj and to_date_obj:
        selected_dates = [d for d in sorted(set(all_dates_objs)) if from_date_obj <= d <= to_date_obj]
    else:
        selected_dates = sorted(set(all_dates_objs))
    selected_dates_str = [d.strftime("%Y-%m-%d") for d in selected_dates]

    student_map = {s["id"]: s["name"] for s in students}
    output = io.StringIO()
    writer = csv.writer(output)

    header = ["Student Name", "Attendance %"] + selected_dates_str
    writer.writerow(header)

    for sid in sorted(selected_student_ids):
        name = student_map.get(sid, f"ID {sid}")
        total = 0
        present = 0
        row = [name]
        att_marks = []
        for d in selected_dates_str:
            raw = attendance.get(d, {})
            if sid in raw:
                mark = "P" if raw[sid]==1 else "A"
                att_marks.append(mark)
                total += 1
                if raw[sid]==1:
                    present += 1
            else:
                att_marks.append("")
        percent = f'{(present/total*100):.1f}' if total > 0 else "N/A"
        row.append(percent)
        row.extend(att_marks)
        writer.writerow(row)

    output.seek(0)
    csv_data = output.read()
    filename = f"attendance_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.route('/admin', methods=['GET'])
def admin_dashboard():
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    students_list = get_all_students()
    return render_template('admin_dashboard.html', students=students_list)

@app.route('/admin/add_student', methods=['POST'])
def add_student():
    global next_student_id, students
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    name = request.form['student_name'].strip()
    if name:
        students.append({"id": next_student_id, "name": name})
        next_student_id += 1
        save_students(students)
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/import_students', methods=['POST'])
def import_students():
    global next_student_id, students
    if 'role' not in session or session['role'] != 'admin':
        flash("Access denied")
        return redirect(url_for('login'))
    file = request.files.get('file')
    if file and file.filename.lower().endswith('.csv'):
        try:
            try:
                content = file.read().decode('utf-8')
            except Exception:
                content = file.read().decode('latin1')
            file.stream.seek(0)
            f = io.StringIO(content)
            reader = csv.reader(f)
            csv_rows = list(reader)
            
            header_row = None
            if csv_rows and (csv_rows[0][0].strip().lower() == 'id' or (len(csv_rows[0]) > 1 and csv_rows[0][1].strip().lower() == 'name')):
                header_row = [col.strip().lower() for col in csv_rows[0]]
                csv_rows = csv_rows[1:]
            
            added = 0
            existing_ids = {s["id"] for s in students}
            existing_names = {s["name"] for s in students}
            
            for row in csv_rows:
                if not row or all(cell.strip() == "" for cell in row): continue
                if header_row:
                    try: id_idx = header_row.index("id")
                    except ValueError: id_idx = -1
                    try: name_idx = header_row.index("name")
                    except ValueError: name_idx = 0
                    
                    sid = None
                    if id_idx != -1 and len(row) > id_idx and row[id_idx].strip():
                        try:
                            sid_candidate = int(row[id_idx].strip())
                            if sid_candidate >= next_student_id: next_student_id = sid_candidate + 1
                            sid = sid_candidate
                        except ValueError: pass
                    
                    name = row[name_idx].strip() if len(row) > name_idx else None
                    if name:
                        if sid is None:
                            sid = next_student_id
                            next_student_id += 1
                        if sid in existing_ids: continue
                        if name in existing_names: continue
                        students.append({"id": sid, "name": name})
                        existing_ids.add(sid)
                        existing_names.add(name)
                        added += 1
                else:
                    name_field = row[0].strip()
                    if name_field and name_field not in existing_names:
                        students.append({"id": next_student_id, "name": name_field})
                        next_student_id += 1
                        added += 1
                        existing_names.add(name_field)
            save_students(students)
            flash(f"Imported {added} students.")
        except Exception:
            flash("Error processing CSV.")
    else:
        flash("Please upload a .csv file.")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_student/<int:student_id>', methods=['POST'])
def delete_student(student_id):
    global students
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    students[:] = [s for s in students if s["id"] != student_id]
    # Remove attendance records for the deleted student
    for adate in list(attendance.keys()):
        if student_id in attendance[adate]:
            del attendance[adate][student_id]
    save_students(students)
    save_attendance(attendance)
    return redirect(url_for('admin_dashboard'))

@app.route('/student_view', methods=['GET'])
def student_view():
    students_list = get_all_students()
    return render_template('student_view_select.html', students=students_list)

@app.route('/student_attendance_public', methods=['GET'])
def student_attendance_public():
    try:
        student_id = int(request.args.get('student_id', ''))
    except:
        flash("Please specify a student")
        return redirect(url_for('student_view'))
    
    # ... (Common calendar logic shared below) ...
    context = get_calendar_context(student_id, request.args.get('year'), request.args.get('month'))
    if not context:
        flash("Student not found.")
        return redirect(url_for('student_view'))

    # DYNAMIC BACK BUTTON: Point to Student View
    return render_template('student_calendar.html', 
                           **context, 
                           back_endpoint='student_view', 
                           back_label='Back to Student View')

@app.route('/student_attendance', methods=['GET'])
def student_attendance():
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    try:
        student_id = int(request.args.get('student_id', ''))
    except:
        flash("Please specify a student")
        return redirect(url_for('admin_dashboard'))

    context = get_calendar_context(student_id, request.args.get('year'), request.args.get('month'))
    if not context:
        flash("Student not found.")
        return redirect(url_for('admin_dashboard'))

    # DYNAMIC BACK BUTTON: Point to Admin Dashboard
    return render_template('student_calendar.html', 
                           **context, 
                           back_endpoint='admin_dashboard', 
                           back_label='Back to Admin')

def get_calendar_context(student_id, year_arg, month_arg):
    # Helper to avoid code duplication between public and admin views
    student_entry = next((s for s in students if s['id'] == student_id), None)
    if not student_entry: return None
    
    today = date.today()
    if not (year_arg and month_arg):
        calendar_year, calendar_month = today.year, today.month
    else:
        calendar_year, calendar_month = int(year_arg), int(month_arg)
        if calendar_month < 1:
            calendar_month = 12
            calendar_year -= 1
        elif calendar_month > 12:
            calendar_month = 1
            calendar_year += 1

    first_day = date(calendar_year, calendar_month, 1)
    _, num_days = calendar.monthrange(calendar_year, calendar_month)
    calendar_grid = []
    week = [None] * first_day.weekday()
    
    for day_num in range(1, num_days + 1):
        day_date = date(calendar_year, calendar_month, day_num)
        day_str = day_date.strftime("%Y-%m-%d")
        att_value = attendance.get(day_str, {}).get(student_id)
        present = att_value if att_value is not None else None
        
        week.append({'day': day_num, 'present': present, 'is_today': (day_date == today)})
        if len(week) == 7:
            calendar_grid.append(week)
            week = []
    if week:
        week.extend([None] * (7 - len(week)))
        calendar_grid.append(week)
        
    prev_month = calendar_month - 1
    prev_year = calendar_year
    if prev_month < 1: prev_month, prev_year = 12, prev_year - 1
    
    next_month = calendar_month + 1
    next_year = calendar_year
    if next_month > 12: next_month, next_year = 1, next_year + 1

    return {
        'student_name': student_entry['name'],
        'student_id': student_id,
        'calendar_grid': calendar_grid,
        'calendar_month': calendar_month,
        'calendar_month_name': calendar.month_name[calendar_month],
        'calendar_year': calendar_year,
        'prev_year': prev_year, 'prev_month': prev_month,
        'next_year': next_year, 'next_month': next_month
    }

if __name__ == '__main__':
    ensure_data_dir()
    # Reload all data once more in case another process changed files between import and run
    students, next_student_id = load_students()
    attendance = load_attendance()
    app.run(host='::', port=80, debug=True)