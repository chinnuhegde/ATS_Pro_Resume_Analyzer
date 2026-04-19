import os
import json
import fitz, docx
from datetime import datetime
from flask import Flask, render_template, request, redirect, session, flash, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key")

# --- DATABASE SETUP ---
database_url = os.environ.get('DATABASE_URL', 'sqlite:///ats_users.db')
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- LOGIN SETUP ---
login_manager = LoginManager(app)
login_manager.login_view = "login"

# --- MODELS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    scans = db.relationship('Scan', backref='owner', lazy=True)

class Scan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    score = db.Column(db.Float)
    feedback = db.Column(db.Text) 
    timestamp = db.Column(db.DateTime, default=datetime.now)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- UTILS ---
def extract_text(file):
    content = ""
    try:
        if file.filename.endswith('.pdf'):
            doc = fitz.open(stream=file.read(), filetype="pdf")
            content = "".join([p.get_text() for p in doc])
        elif file.filename.endswith('.docx'):
            doc = docx.Document(file)
            content = "\n".join([p.text for p in doc.paragraphs])
    except Exception as e:
        print(f"Extraction Error: {e}")
    return content

# --- ROUTES ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/dashboard', methods=['GET','POST'])
def dashboard():
    if request.method == 'POST':
        # 1. Input Check
        if 'resume' not in request.files or not request.form.get('jd'):
            flash("Upload a resume and paste a JD.", "danger")
            return redirect(request.url)
            
        file = request.files['resume']
        jd_text = request.form['jd']
        resume_text = extract_text(file)
        
        if not resume_text.strip():
            flash("Could not read file.", "danger")
            return redirect(request.url)

        # 2. LOCAL IMPORT (Solves 404 issues)
        from rag_pipeline import ask_rag
        
        # 3. Call RAG
        rag_data = ask_rag(resume_text, jd_text)

        if rag_data:
            score = float(rag_data.get('score', 0))
            missing = rag_data.get('missing_skills', [])
            suggestions = rag_data.get('suggestions', [])
            feedback_list = [rag_data.get('analysis', "Analysis complete.")]
            
            session['result'] = {
                'score': score, 'missing': missing, 
                'suggestions': suggestions, 'feedback': feedback_list
            }

            if current_user.is_authenticated:
                full_json = json.dumps({'missing': missing, 'suggestions': suggestions, 'feedback': feedback_list})
                db.session.add(Scan(user_id=current_user.id, score=score, feedback=full_json))
                db.session.commit()
            
            return redirect(url_for('result'))
        else:
            flash("AI analysis failed. Check your API key.", "warning")
            
    return render_template('dashboard.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form['email']).first()
        if user and check_password_hash(user.password, request.form['password']):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash("Login failed.", "danger")
    return render_template('login.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        if User.query.filter_by(email=email).first():
            flash("Email exists.", "warning")
            return redirect(url_for('login'))
        
        hashed_pw = generate_password_hash(request.form['password'], method='pbkdf2:sha256')
        new_user = User(email=email, password=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('dashboard'))
    return render_template('register.html')

@app.route('/result')
def result():
    if 'result' not in session:
        return redirect(url_for('dashboard'))
    return render_template('result.html', data=session.get('result'))

@app.route('/scan/<int:scan_id>')
@login_required
def view_scan(scan_id):
    scan = Scan.query.filter_by(id=scan_id, user_id=current_user.id).first_or_404()
    
    try:
        data = json.loads(scan.feedback)
        result_data = {
            'score': scan.score,
            'missing': data.get('missing', []),
            'suggestions': data.get('suggestions', []),
            'feedback': data.get('feedback', [])
        }
    except json.JSONDecodeError:
        # Fallback for old database entries before the JSON upgrade
        result_data = {
            'score': scan.score,
            'missing': [],
            'suggestions': ["No detailed insights available for this older scan."],
            'feedback': scan.feedback.split(' | ')
        }
        
    return render_template('result.html', data=result_data, is_history=True)

@app.route('/history')
@login_required
def history():
    scans = Scan.query.filter_by(user_id=current_user.id).order_by(Scan.timestamp.desc()).all()
    
    parsed_scans = []
    for s in scans:
        try:
            data = json.loads(s.feedback)
            # Grab the first sentence of the analysis for the summary preview
            summary = data.get('feedback', [''])[0][:85] + "..."
        except json.JSONDecodeError:
            summary = s.feedback[:85] + "..."
            
        parsed_scans.append({
            'id': s.id,
            'timestamp': s.timestamp,
            'score': s.score,
            'summary': summary
        })
        
    return render_template('history.html', scans=parsed_scans)

@app.route('/logout')
@login_required
def logout():
    session.pop('result', None)
    logout_user()
    return redirect(url_for('home'))

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=10000, debug=True)