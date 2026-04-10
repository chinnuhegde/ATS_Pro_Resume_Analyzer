# 🚀 ATS Pro: AI-Powered Resume Analyzer

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/Framework-Flask-lightgrey.svg)](https://flask.palletsprojects.com/)
[![AI](https://img.shields.io/badge/AI-Gemini%202.5%20Flash-orange.svg)](https://ai.google.dev/)

**ATS Pro** is a high-performance web application designed to help job seekers bypass Applicant Tracking Systems (ATS). Using **Google Gemini 2.5 Flash**, it provides recruiter-level analysis of how well a resume matches a job description.

---

## 🔥 Core Features

- **Intelligent Scoring:** Get an instant compatibility score out of 100  
- **Keyword Analysis:** Automatically identifies missing technical and soft skills  
- **AI Feedback:** Get 3 actionable suggestions from a virtual recruiter  
- **Dual Format Support:** Works with `.pdf` and `.docx`  
- **Secure Authentication:** OTP verification via Gmail  
- **Scan History:** Track previous resume analyses  

---

## 🛠️ Tech Stack

- **Backend:** Python, Flask  
- **Database:** SQLAlchemy (PostgreSQL on Render | SQLite locally)  
- **AI Engine:** Google Gemini 2.5 Flash  
- **Authentication:** Flask-Login & Werkzeug  
- **Mail Service:** Flask-Mail (SMTP)  
- **Parsing:** PyMuPDF (`fitz`), python-docx  

---

## ⚙️ Local Setup Instructions

### 1. Clone the Repository
```bash
git clone https://github.com/chinnuhegde/ATS_Pro_Resume_Analyzer.git
cd ATS_Pro_Resume_Analyzer
```

### 2. Create Virtual Environment
```bash
python -m venv venv

# Windows:
venv\Scripts\activate

# Mac/Linux:
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Setup Environment Variables
Create a `.env` file in the root folder:

```
FLASK_SECRET_KEY=your_random_secret_string
DATABASE_URL=sqlite:///ats_users.db
MAIL_USERNAME=your_email@gmail.com
MAIL_PASSWORD=your_app_password
GEMINI_API_KEY=your_gemini_api_key
```

### 5. Run the Application
```bash
python app.py
```

---

## ☁️ Deployment (Render)

- **Build Command:**  
```bash
pip install -r requirements.txt
```

- **Start Command:**  
```bash
gunicorn -w 2 app:app
```

> ⚠️ Add all environment variables in Render dashboard

---

## 🛡️ Security Features

- No hardcoded secrets (uses `.env`)
- `.gitignore` prevents credential leaks  
- Password hashing using Werkzeug  

---

## 👤 Author

**Chinmay Hegde**  
