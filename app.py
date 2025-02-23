from flask import Flask, render_template, request, redirect, url_for, send_from_directory, session, flash
import os
import sqlite3
from datetime import datetime, timedelta
from textblob import TextBlob
import hashlib
import json

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Change for production
UPLOAD_FOLDER = 'uploads'
BLOCKCHAIN_FILE = 'blockchain.json'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
if not os.path.exists(BLOCKCHAIN_FILE):
    with open(BLOCKCHAIN_FILE, 'w') as f:
        json.dump([], f)

@app.template_filter('basename')
def basename_filter(path):
    return os.path.basename(path) if path else ''

def init_db():
    conn = sqlite3.connect('capsules.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY, email TEXT UNIQUE, password TEXT, username TEXT, points INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS capsules 
                 (id INTEGER PRIMARY KEY, user_id INTEGER, text TEXT, image TEXT, audio TEXT, 
                  unlock_date TEXT, sentiment TEXT, category TEXT, password TEXT, note TEXT, 
                  expire_date TEXT, created_at TEXT, title TEXT, mood TEXT, visibility TEXT, 
                  tags TEXT, likes INTEGER DEFAULT 0, comments TEXT)''')
    for column in ['audio', 'category', 'password', 'note', 'expire_date', 'created_at', 'title', 'mood', 'visibility', 'tags', 'likes', 'comments']:
        c.execute("PRAGMA table_info(capsules)")
        if column not in [col[1] for col in c.fetchall()]:
            c.execute(f"ALTER TABLE capsules ADD COLUMN {column} TEXT DEFAULT ''")
    conn.commit()
    conn.close()

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()  # Handle empty or whitespace-only input
        password = request.form.get('password', '').strip()
        
        if not email or not password:
            flash('Email and password are required', 'error')
            return render_template('login.html')

        try:
            conn = sqlite3.connect('capsules.db')
            c = conn.cursor()
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            c.execute("SELECT id, username FROM users WHERE email = ? AND password = ?", (email, password_hash))
            user = c.fetchone()
            conn.close()
            
            if user:
                session['user_id'] = user[0]
                session['username'] = user[1]
                flash('Logged in successfully!', 'success')  # Optional: Add success message
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid credentials', 'error')
        except sqlite3.Error as e:
            flash(f'Database error: {str(e)}', 'error')
            return render_template('login.html')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        username = request.form.get('username', '').strip()
        
        if not email or not password or not username:
            flash('All fields are required', 'error')
            return render_template('signup.html')

        try:
            conn = sqlite3.connect('capsules.db')
            c = conn.cursor()
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            try:
                c.execute("INSERT INTO users (email, password, username) VALUES (?, ?, ?)", (email, password_hash, username))
                conn.commit()
                user_id = c.lastrowid
                session['user_id'] = user_id
                session['username'] = username
                flash('Signed up successfully!', 'success')
                return redirect(url_for('dashboard'))
            except sqlite3.IntegrityError:
                flash('Email already exists', 'error')
            finally:
                conn.close()
        except sqlite3.Error as e:
            flash(f'Database error: {str(e)}', 'error')
            return render_template('signup.html')
    return render_template('signup.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect('capsules.db')
    c = conn.cursor()
    try:
        c.execute("SELECT COUNT(*), points FROM users WHERE id = ?", (session['user_id'],))
        user_data = c.fetchone()
        capsule_count, points = user_data if user_data else (0, 0)
        c.execute("SELECT COUNT(*) FROM capsules WHERE user_id = ? AND unlock_date <= ? AND (expire_date IS NULL OR expire_date >= ?)", 
                  (session['user_id'], datetime.now().strftime('%Y-%m-%d'), datetime.now().strftime('%Y-%m-%d')))
        unlocked_count = c.fetchone()[0]
    except sqlite3.Error as e:
        flash(f'Database error: {str(e)}', 'error')
        unlocked_count = 0
    finally:
        conn.close()
    return render_template('dashboard.html', username=session['username'], capsule_count=capsule_count, points=points, unlocked_count=unlocked_count)

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect('capsules.db')
    c = conn.cursor()
    try:
        c.execute("SELECT email, username FROM users WHERE id = ?", (session['user_id'],))
        user = c.fetchone()
        if not user:
            conn.close()
            flash('User not found', 'error')
            return redirect(url_for('login'))

        current_email, username = user
        if request.method == 'POST':
            action = request.form.get('action')
            current_password = request.form.get('current_password', '').strip()
            if not current_password:
                flash('Current password is required', 'error')
            else:
                c.execute("SELECT password FROM users WHERE id = ?", (session['user_id'],))
                stored_password = c.fetchone()[0]
                if hashlib.sha256(current_password.encode()).hexdigest() != stored_password:
                    flash('Incorrect current password', 'error')
                    conn.close()
                    return render_template('settings.html', email=current_email, username=username)

            if action == 'update_email':
                new_email = request.form.get('new_email', '').strip()
                if new_email:
                    try:
                        c.execute("UPDATE users SET email = ? WHERE id = ?", (new_email, session['user_id']))
                        conn.commit()
                        flash('Email updated successfully!', 'success')
                    except sqlite3.IntegrityError:
                        flash('Email already in use', 'error')
            elif action == 'update_password':
                new_password = request.form.get('new_password', '').strip()
                if new_password:
                    hashed_new_password = hashlib.sha256(new_password.encode()).hexdigest()
                    c.execute("UPDATE users SET password = ? WHERE id = ?", (hashed_new_password, session['user_id']))
                    conn.commit()
                    flash('Password updated successfully!', 'success')
            elif action == 'delete_account':
                if request.form.get('confirm') == 'yes':
                    c.execute("DELETE FROM capsules WHERE user_id = ?", (session['user_id'],))
                    c.execute("DELETE FROM users WHERE id = ?", (session['user_id'],))
                    conn.commit()
                    session.pop('user_id', None)
                    session.pop('username', None)
                    conn.close()
                    flash('Account deleted successfully!', 'success')
                    return redirect(url_for('login'))
                flash('Please confirm account deletion', 'error')
            conn.close()
            return redirect(url_for('settings'))
    except sqlite3.Error as e:
        flash(f'Database error: {str(e)}', 'error')
        conn.close()
        return render_template('settings.html', email=current_email, username=username)
    conn.close()
    return render_template('settings.html', email=current_email, username=username)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/add', methods=['POST'])
def add_capsule():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    text = request.form.get('text', '').strip()
    unlock_date = request.form.get('unlock_date', '').strip()
    expire_date = request.form.get('expire_date', '').strip() or None
    category = request.form.get('category', 'Personal')  # Default to Personal
    password = request.form.get('password', '').strip()
    title = request.form.get('title', '').strip()
    mood = request.form.get('mood', '').strip()
    visibility = request.form.get('visibility', 'Private')  # Default to Private
    image = request.files.get('image')
    audio = request.files.get('audio')

    if not title or not unlock_date:
        flash('Title and unlock date are required', 'error')
        return redirect(url_for('index'))

    try:
        image_path = None
        if image and image.filename:
            image_path = os.path.join(UPLOAD_FOLDER, image.filename)
            image.save(image_path)
            tags = mock_photo_tagging(image_path)  # AI/ML: Mock photo tagging
        else:
            tags = None

        audio_path = None
        if audio and audio.filename:
            audio_path = os.path.join(UPLOAD_FOLDER, audio.filename)
            audio.save(audio_path)

        sentiment = "Neutral"
        if text:
            blob = TextBlob(text)
            polarity = blob.sentiment.polarity
            sentiment = "Very Positive" if polarity > 0.5 else "Positive" if polarity > 0 else "Very Negative" if polarity < -0.5 else "Negative" if polarity < 0 else "Neutral"

        password_hash = hashlib.sha256(password.encode()).hexdigest() if password else None
        created_at = datetime.now().strftime('%Y-%m-%d')
        capsule_data = f"{text}{image_path}{audio_path}{unlock_date}".encode()
        blockchain_hash = hashlib.sha256(capsule_data).hexdigest()

        conn = sqlite3.connect('capsules.db')
        c = conn.cursor()
        c.execute("INSERT INTO capsules (user_id, text, image, audio, unlock_date, sentiment, category, password, created_at, expire_date, title, mood, visibility, tags, comments, likes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  (session['user_id'], text, image_path, audio_path, unlock_date, sentiment, category, password_hash, created_at, expire_date, title, mood, visibility, ','.join(tags) if tags else None, '', 0))
        capsule_id = c.lastrowid
        c.execute("UPDATE users SET points = points + 10 WHERE id = ?", (session['user_id'],))  # Gamification: Points for creation
        conn.commit()
        conn.close()

        # Blockchain: Store hash (not visible to users)
        with open(BLOCKCHAIN_FILE, 'r') as f:
            blockchain = json.load(f)
        blockchain.append({"id": capsule_id, "hash": blockchain_hash, "timestamp": created_at, "user_id": session['user_id']})
        with open(BLOCKCHAIN_FILE, 'w') as f:
            json.dump(blockchain, f)

        flash('Capsule created successfully!', 'success')
        return redirect(url_for('view_capsules'))
    except sqlite3.Error as e:
        flash(f'Database error: {str(e)}', 'error')
        return redirect(url_for('index'))
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/capsules')
def view_capsules():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect('capsules.db')
    c = conn.cursor()
    try:
        c.execute("SELECT id, text, image, audio, unlock_date, sentiment, category, password, note, expire_date, created_at, title, mood, visibility, tags, likes, comments FROM capsules WHERE user_id = ? OR visibility = 'Public'", (session['user_id'],))
        capsules = c.fetchall()
        # Fetch leaderboard before closing connection
        c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
        leaderboard = c.fetchall()
    except sqlite3.Error as e:
        flash(f'Database error: {str(e)}', 'error')
        capsules = []
        leaderboard = []
    finally:
        conn.close()

    current_date = datetime.now().strftime('%Y-%m-%d')
    capsules = [c for c in capsules if not c[9] or c[9] >= current_date]

    total_capsules = len([c for c in capsules if c[13] == 'Private' or c[0] == session['user_id']])
    positive_count = sum(1 for c in capsules if "Positive" in c[5])
    badges = []
    if total_capsules >= 3:
        badges.append("Memory Keeper")
    if positive_count > total_capsules / 2:
        badges.append("Optimist")
    if total_capsules >= 5:
        badges.append("Time Master")
    streak = calculate_streak([c[10] for c in capsules if c[13] == 'Private' or c[0] == session['user_id']])

    return render_template('capsules.html', capsules=capsules, current_date=current_date, badges=badges, streak=streak, leaderboard=leaderboard)

@app.route('/community')
def community_feed():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect('capsules.db')
    c = conn.cursor()
    try:
        c.execute("SELECT c.id, c.text, c.image, c.audio, c.unlock_date, c.sentiment, c.category, c.password, c.note, c.expire_date, c.created_at, c.title, c.mood, c.visibility, c.tags, c.likes, c.comments, u.username FROM capsules c JOIN users u ON c.user_id = u.id WHERE c.visibility = 'Public' AND (c.expire_date IS NULL OR c.expire_date >= ?)", (datetime.now().strftime('%Y-%m-%d'),))
        public_capsules = c.fetchall()
    except sqlite3.Error as e:
        flash(f'Database error: {str(e)}', 'error')
        public_capsules = []
    finally:
        conn.close()

    current_date = datetime.now().strftime('%Y-%m-%d')
    public_capsules = [c for c in public_capsules if not c[8] or c[8] >= current_date]

    return render_template('community.html', capsules=public_capsules, current_date=current_date)

@app.route('/capsule/<int:capsule_id>', methods=['GET', 'POST'])
def view_capsule(capsule_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect('capsules.db')
    c = conn.cursor()
    try:
        c.execute("SELECT id, text, image, audio, unlock_date, sentiment, category, password, note, expire_date, title, mood, visibility, tags, likes, comments FROM capsules WHERE id = ?", (capsule_id,))
        capsule = c.fetchone()
        if not capsule or (capsule[9] and capsule[9] < datetime.now().strftime('%Y-%m-%d')):
            conn.close()
            flash('Capsule not found or expired', 'error')
            return redirect(url_for('view_capsules'))

        current_date = datetime.now().strftime('%Y-%m-%d')
        if capsule[4] > current_date:
            conn.close()
            return "Capsule is still locked", 403

        if request.method == 'POST':
            action = request.form.get('action')
            password = request.form.get('password', '').strip()
            comment = request.form.get('comment', '').strip()
            if action == 'like':
                c.execute("UPDATE capsules SET likes = likes + 1 WHERE id = ?", (capsule_id,))
                c.execute("UPDATE users SET points = points + 3 WHERE id = ?", (session['user_id'],))  # Gamification: Points for liking
                conn.commit()
            elif action == 'comment' and comment:
                c.execute("SELECT comments FROM capsules WHERE id = ?", (capsule_id,))
                existing_comments = c.fetchone()[0] or ''
                new_comments = f"{existing_comments}\n{session['username']}: {comment}"
                c.execute("UPDATE capsules SET comments = ? WHERE id = ?", (new_comments, capsule_id))
                c.execute("UPDATE users SET points = points + 5 WHERE id = ?", (session['user_id'],))  # Gamification: Points for commenting
                conn.commit()
            elif action == 'contribute':
                text = request.form.get('contribute_text', '').strip()
                if text and capsule[12] == 'Public':
                    c.execute("SELECT text FROM capsules WHERE id = ?", (capsule_id,))
                    existing_text = c.fetchone()[0] or ''
                    new_text = f"{existing_text}\n{session['username']}: {text}"
                    c.execute("UPDATE capsules SET text = ? WHERE id = ?", (new_text, capsule_id))
                    c.execute("UPDATE users SET points = points + 20 WHERE id = ?", (session['user_id'],))  # Gamification: Points for contribution
                    conn.commit()
            elif action == 'delete':
                if capsule[0] == session['user_id'] or capsule[12] == 'Private':  # Only owner can delete private capsules
                    c.execute("DELETE FROM capsules WHERE id = ?", (capsule_id,))
                    conn.commit()
                    flash('Capsule deleted successfully!', 'success')
                    conn.close()
                    return redirect(url_for('view_capsules'))
                flash('You can only delete your private capsules.', 'error')
            elif capsule[7]:
                if hashlib.sha256(password.encode()).hexdigest() != capsule[7]:
                    flash('Incorrect password', 'error')
                    conn.close()
                    return render_template('view.html', capsule=capsule, current_date=current_date)
                note = request.form.get('note', '').strip()
                c.execute("UPDATE capsules SET note = ? WHERE id = ?", (note, capsule_id))
                c.execute("UPDATE users SET points = points + 5 WHERE id = ?", (session['user_id'],))  # Gamification: Points for note
                conn.commit()
                flash('Note saved!', 'success')
            conn.close()
            return redirect(url_for('view_capsule', capsule_id=capsule_id))
    except sqlite3.Error as e:
        flash(f'Database error: {str(e)}', 'error')
        conn.close()
        return redirect(url_for('view_capsules'))
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        conn.close()
        return redirect(url_for('view_capsules'))

    return render_template('view.html', capsule=capsule, current_date=current_date)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    flash('Logged out successfully!', 'success')
    return redirect(url_for('login'))

def calculate_streak(dates):
    if not dates:
        return 0
    dates = sorted(set(dates))
    streak = 1
    for i in range(1, len(dates)):
        if (datetime.strptime(dates[i], '%Y-%m-%d') - datetime.strptime(dates[i-1], '%Y-%m-%d')).days == 1:
            streak += 1
        else:
            break
    return streak

def mock_photo_tagging(image_path):
    # Mock AI/ML: Generic memory-related tags
    return ["Memory", "Photo", "Personal"]  # Generic tags

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)