import os
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from authlib.integrations.flask_client import OAuth
import google.generativeai as genai
from PyPDF2 import PdfReader
from jobspy import scrape_jobs
from apscheduler.schedulers.background import BackgroundScheduler
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "super_secret_dev_key")

# Database Configuration (SQLite for local/Render, can be swapped to Postgres)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL", "sqlite:///jobs.db")
if app.config['SQLALCHEMY_DATABASE_URI'].startswith("postgres://"):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'home'

# Configure Gemini
genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))

# Configure OAuth
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    access_token_url='https://accounts.google.com/o/oauth2/token',
    access_token_params=None,
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    authorize_params=None,
    api_base_url='https://www.googleapis.com/oauth2/v1/',
    client_kwargs={'scope': 'openid email profile'},
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration'
)

# --- DATABASE MODELS ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(120))
    avatar = db.Column(db.String(255))
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class JobHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200))
    company = db.Column(db.String(200))
    location = db.Column(db.String(200))
    url = db.Column(db.String(500))
    date_found = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- HELPER FUNCTIONS ---

def extract_text_from_pdf(pdf_file):
    reader = PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

def analyze_resume_with_ai(resume_text):
    try:
        model = genai.GenerativeModel('gemini-pro')
        prompt = f"""
        You are an expert tech recruiter and ATS system.
        Read the following resume text and provide exactly two things in valid JSON format:
        1. "search_terms": An array of 2 or 3 highly specific job titles to search for (e.g., ["Python Developer Fresher", "Junior Data Analyst"]).
        2. "suggestions": An array of 2 or 3 short, actionable bullet points on how they can improve this resume for ATS systems.
        
        Resume text:
        {resume_text[:4000]}
        
        Return ONLY valid JSON.
        """
        response = model.generate_content(prompt)
        result_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(result_text)
    except Exception as e:
        logger.error(f"Error calling Gemini AI: {e}")
        return {
            "search_terms": ["Software Developer", "Data Analyst"],
            "suggestions": ["Ensure your contact information is clearly visible at the top.", "Use strong action verbs to describe your projects."]
        }

# --- VIP AUTOMATION TASK ---

def run_daily_vip_job():
    """Runs daily. Finds the admin user and emails them personalized jobs."""
    with app.app_context():
        # Find Sudip (Admin)
        admin_email = os.environ.get("ADMIN_EMAIL", "adaksudip956@gmail.com")
        admin = User.query.filter_by(email=admin_email).first()
        
        if not admin:
            logger.info("Admin user not yet registered in database. Skipping daily automation.")
            return

        logger.info(f"Running daily VIP job for {admin.email}...")
        
        # Define Sudip's specific search criteria
        search_terms = ["Software Developer Fresher", "Data Analyst Entry Level", "MCA Fresher IT"]
        location = "India"
        
        all_jobs = []
        for term in search_terms:
            try:
                jobs_df = scrape_jobs(
                    site_name=["indeed", "linkedin"],
                    search_term=term,
                    location=location,
                    results_wanted=3,
                    country_indeed='India'
                )
                if not jobs_df.empty:
                    for _, row in jobs_df.iterrows():
                        job = {
                            "title": row.get('title', 'Unknown'),
                            "company": row.get('company', 'Unknown'),
                            "location": row.get('location', location),
                            "url": row.get('job_url', '#')
                        }
                        all_jobs.append(job)
                        
                        # Save to history
                        new_history = JobHistory(
                            user_id=admin.id,
                            title=job['title'],
                            company=job['company'],
                            location=job['location'],
                            url=job['url']
                        )
                        db.session.add(new_history)
            except Exception as e:
                logger.error(f"Error scraping {term} in background: {e}")
                
        db.session.commit()
        
        # Send Email
        gmail_user = os.environ.get("GMAIL_USER")
        gmail_pass = os.environ.get("GMAIL_APP_PASSWORD")
        
        if gmail_user and gmail_pass and all_jobs:
            send_email_digest(gmail_user, gmail_pass, admin.email, all_jobs)

def send_email_digest(sender, password, recipient, jobs):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"🚀 Your AI Job Matcher Daily Digest - Found {len(jobs)} Roles"
    msg['From'] = sender
    msg['To'] = recipient

    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; background-color: #030712; color: #fff; padding: 20px;">
        <h2 style="color: #06b6d4;">Sudip's Automated VIP Job Bot</h2>
        <p>Good morning! I found {len(jobs)} fresh opportunities for you today.</p>
        <table style="width: 100%; border-collapse: collapse; margin-top: 20px;">
          <tr>
            <th style="border-bottom: 1px solid #333; text-align: left; padding: 10px; color: #9ca3af;">Job Title</th>
            <th style="border-bottom: 1px solid #333; text-align: left; padding: 10px; color: #9ca3af;">Company</th>
            <th style="border-bottom: 1px solid #333; text-align: left; padding: 10px; color: #9ca3af;">Action</th>
          </tr>
    """
    for j in jobs:
        html += f"""
          <tr>
            <td style="padding: 10px; border-bottom: 1px solid #222;">{j['title']}</td>
            <td style="padding: 10px; border-bottom: 1px solid #222; color: #06b6d4;">{j['company']}</td>
            <td style="padding: 10px; border-bottom: 1px solid #222;">
                <a href="{j['url']}" style="background: #10b981; color: #000; padding: 5px 10px; text-decoration: none; border-radius: 4px;">Apply</a>
            </td>
          </tr>
        """
    html += """
        </table>
        <p style="margin-top: 20px; color: #9ca3af;">Log in to your Dashboard to view your complete history.</p>
      </body>
    </html>
    """
    msg.attach(MIMEText(html, 'html'))
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, recipient, msg.as_string())
        server.quit()
        logger.info(f"Successfully sent daily digest to {recipient}")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")

# Start Background Scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(func=run_daily_vip_job, trigger="cron", hour=9, minute=0) # Runs every day at 9 AM
scheduler.start()

# --- WEB ROUTES ---

@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('landing.html')

@app.route('/login')
def login():
    if not os.environ.get("GOOGLE_CLIENT_ID"):
        # For testing without Google OAuth credentials yet, bypass login
        return render_template('error.html', message="Google Login is not configured yet. Set GOOGLE_CLIENT_ID in your environment variables.")
    redirect_uri = url_for('authorize', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/authorize')
def authorize():
    token = google.authorize_access_token()
    user_info = google.get('userinfo').json()
    
    email = user_info['email']
    user = User.query.filter_by(email=email).first()
    
    if not user:
        # Create new user
        is_admin = (email == os.environ.get("ADMIN_EMAIL", "adaksudip956@gmail.com"))
        user = User(
            email=email,
            name=user_info.get('name', ''),
            avatar=user_info.get('picture', ''),
            is_admin=is_admin
        )
        db.session.add(user)
        db.session.commit()
        
    login_user(user)
    return redirect(url_for('dashboard'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/dashboard')
@login_required
def dashboard():
    history = JobHistory.query.filter_by(user_id=current_user.id).order_by(JobHistory.date_found.desc()).all()
    return render_template('dashboard.html', user=current_user, history=history)

@app.route('/api/analyze', methods=['POST'])
@login_required
def analyze_resume():
    if 'resume' not in request.files:
        return jsonify({"error": "No resume file provided"}), 400
        
    file = request.files['resume']
    if file.filename == '':
        return jsonify({"error": "Empty filename"}), 400
        
    try:
        resume_text = extract_text_from_pdf(file)
        if not resume_text.strip():
            return jsonify({"error": "Could not extract text from PDF."}), 400
            
        ai_analysis = analyze_resume_with_ai(resume_text)
        return jsonify({"success": True, "data": ai_analysis})
    except Exception as e:
        logger.error(f"Error processing resume: {e}")
        return jsonify({"error": "Failed to process resume"}), 500

@app.route('/api/search', methods=['POST'])
@login_required
def search_jobs():
    data = request.json
    search_terms = data.get('search_terms', [])
    location = data.get('location', "India")
    
    all_jobs = []
    try:
        for term in search_terms:
            jobs_df = scrape_jobs(
                site_name=["indeed", "linkedin"],
                search_term=term,
                location=location,
                results_wanted=5,
                country_indeed='India' if "India" in location else None
            )
            
            if not jobs_df.empty:
                for _, row in jobs_df.iterrows():
                    job = {
                        "title": row.get('title', 'Unknown'),
                        "company": row.get('company', 'Unknown'),
                        "location": row.get('location', location),
                        "url": row.get('job_url', '#'),
                        "source": term
                    }
                    all_jobs.append(job)
                    
                    # Save to user history
                    new_history = JobHistory(
                        user_id=current_user.id,
                        title=job['title'],
                        company=job['company'],
                        location=job['location'],
                        url=job['url']
                    )
                    db.session.add(new_history)
        
        db.session.commit()
        return jsonify({"success": True, "jobs": all_jobs})
    except Exception as e:
        logger.error(f"Error scraping jobs: {e}")
        return jsonify({"error": "Failed to scrape jobs."}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all() # Initialize database
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    app.run(debug=True, port=5000, use_reloader=False) # use_reloader=False prevents double scheduler trigger
