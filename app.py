from flask import Flask, render_template, request, redirect, session, flash, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin, current_user
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import fitz, docx, random, os, json
import google.generativeai as genai
from dotenv import load_dotenv

# Load hidden keys from .env file
load_dotenv()

# ---------------- APP ----------------
app = Flask(__name__)
# Securely load the Flask secret key
app.secret_key = os.environ.get("FLASK_SECRET_KEY")

# ---------------- DATABASE SETUP ----------------
database_url = os.environ.get('DATABASE_URL')

# This part is critical for Render/Heroku compatibility
if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
else:
    # Fallback to local sqlite if DATABASE_URL is missing
    database_url = 'sqlite:///ats_users.db'

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ---------------- LOGIN ----------------
login_manager = LoginManager(app)
login_manager.login_view = "login"

# ---------------- MAIL ----------------
app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME=os.environ.get('MAIL_USERNAME'),
    MAIL_PASSWORD=os.environ.get('MAIL_PASSWORD')
)
mail = Mail(app)

# ---------------- GEMINI AI SETUP ----------------
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

# ---------------- MODELS ----------------
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

with app.app_context():
    db.create_all()


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ---------------- UTILITIES ----------------
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
        print(f"File Extraction Error: {e}")
    return content

def get_gemini_analysis(resume_text, jd_text):
    prompt = f"""
    You are an expert Applicant Tracking System (ATS) and Senior Technical Recruiter.
    Analyze the following Resume against the provided Job Description.
    
    Return ONLY a valid JSON object. Do NOT include markdown formatting like ```json.
    Strictly limit suggestions to 3 points and feedback to 3 concise sentences.
    
    The JSON must have this exact structure:
    {{
        "score": 85.5,
        "missing": ["aws", "docker"],
        "suggestions": ["Add more metrics", "Highlight leadership", "Quantify results"],
        "feedback": [
            "Strong candidate with solid technical fundamentals.",
            "Lacks direct experience with cloud deployment.",
            "Education matches the job requirements perfectly."
        ]
    }}

    Job Description:
    {jd_text}
    
    Resume:
    {resume_text}
    """
    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.2 
            )
        )
        raw_text = response.text.strip()
        
        if raw_text.startswith("```json"):
            raw_text = raw_text.replace("```json", "", 1)
        if raw_text.startswith("```"):
            raw_text = raw_text.replace("```", "", 1)
        if raw_text.endswith("```"):
            raw_text = raw_text[::-1].replace("```"[::-1], "", 1)[::-1]
            
        raw_text = raw_text.strip()
        analysis_data = json.loads(raw_text)
        
        return (
            float(analysis_data.get('score', 0)),
            analysis_data.get('missing', []),
            analysis_data.get('suggestions', []),
            analysis_data.get('feedback', ["Analysis complete."])
        )
    except Exception as e:
        error_message = str(e).lower()
        print(f"CRITICAL GEMINI ERROR: {error_message}")
        
        if "429" in error_message or "quota" in error_message or "exhausted" in error_message:
            return (
                0.0,
                ["API Limit Reached"],
                ["Please wait a minute and try your scan again.", "Our free AI engine is currently handling maximum traffic."],
                ["We apologize! We are currently experiencing high traffic and have temporarily hit the limit of our free AI processing tier. Please give it a few moments and try analyzing your resume again."]
            )
        else:
            return (
                0.0,
                ["Processing Error"],
                ["Check if your resume text is easily readable.", "Try uploading a different PDF/DOCX format."],
                ["We encountered an unexpected error while reading your resume or job description. Please check your files and try again."]
            )

# ---------------- ROUTES ----------------
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        if User.query.filter_by(email=request.form['email']).first():
            flash("Email already registered.", "warning")
            return redirect(url_for('login'))

        hashed_pw = generate_password_hash(request.form['password'], method='pbkdf2:sha256')
        session['reg_data'] = {'email': request.form['email'], 'pw': hashed_pw}
        otp = str(random.randint(100000, 999999))
        session['otp'] = otp
        
        try:
            msg = Message("Verify your ATS Pro Account", sender=app.config['MAIL_USERNAME'], recipients=[request.form['email']])
            msg.body = f"Your verification code is: {otp}"
            mail.send(msg)
            return redirect(url_for('verify'))
        except Exception as e:
            print(f"Mail Error: {e}")
            flash("Error sending verification email. Check your credentials.", "danger")
            
    return render_template('register.html')

@app.route('/verify', methods=['GET','POST'])
def verify():
    if request.method == 'POST':
        if request.form['otp'] == session.get('otp'):
            data = session.get('reg_data')
            new_user = User(email=data['email'], password=data['pw'])
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)
            
            if 'result' in session:
                res = session['result']
                full_data = json.dumps({
                    'missing': res.get('missing', []),
                    'suggestions': res.get('suggestions', []),
                    'feedback': res.get('feedback', [])
                })
                new_scan = Scan(user_id=new_user.id, score=res['score'], feedback=full_data)
                db.session.add(new_scan)
                db.session.commit()
                flash("Registration successful! We saved your scan and unlocked your detailed insights.", "success")
                return redirect(url_for('result'))
            
            flash("Registration successful! Welcome to ATS Pro.", "success")
            return redirect(url_for('dashboard'))
            
        flash("Invalid OTP. Please try again.", "danger")
    return render_template('verify.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form['email']).first()
        if user and check_password_hash(user.password, request.form['password']):
            login_user(user)
            
            if 'result' in session:
                res = session['result']
                full_data = json.dumps({
                    'missing': res.get('missing', []),
                    'suggestions': res.get('suggestions', []),
                    'feedback': res.get('feedback', [])
                })
                new_scan = Scan(user_id=user.id, score=res['score'], feedback=full_data)
                db.session.add(new_scan)
                db.session.commit()
                flash("Welcome back! We saved your scan and unlocked your detailed insights.", "success")
                return redirect(url_for('result'))
            
            return redirect(url_for('dashboard'))
            
        flash("Invalid credentials. Please check your email and password.", "danger")
    return render_template('login.html')

@app.route('/dashboard', methods=['GET','POST'])
def dashboard():
    if request.method == 'POST':
        if 'resume' not in request.files:
            flash("No file uploaded", "danger")
            return redirect(request.url)
            
        file = request.files['resume']
        jd = request.form['jd']
        
        if file.filename == '':
            flash("No selected file", "danger")
            return redirect(request.url)

        text = extract_text(file)
        if not text.strip():
            flash("Could not extract text. Make sure it's a valid PDF/DOCX.", "danger")
            return redirect(request.url)
        
        score, missing, suggestions, feedback_list = get_gemini_analysis(text, jd)
        session['result'] = {
            'score': score, 
            'missing': missing, 
            'suggestions': suggestions, 
            'feedback': feedback_list
        }
        
        if current_user.is_authenticated:
            full_data = json.dumps({
                'missing': missing,
                'suggestions': suggestions,
                'feedback': feedback_list
            })
            new_scan = Scan(user_id=current_user.id, score=score, feedback=full_data)
            db.session.add(new_scan)
            db.session.commit()
        
        return redirect(url_for('result'))
        
    return render_template('dashboard.html')

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
            summary = data.get('feedback', [''])[0][:85]
        except json.JSONDecodeError:
            summary = s.feedback[:85]
            
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
    flash("You have been logged out.", "info")
    return redirect(url_for('home'))

if __name__ == "__main__":
    app.run(debug=True)