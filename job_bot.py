import os
import smtplib
import imaplib
import time
import json
import datetime
from email.message import EmailMessage
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jobspy import scrape_jobs

# ==========================================
# SUDIP'S AUTOMATED JOB BOT & GMAIL DRAFTER
# ==========================================

MY_NAME = "Sudip Kumar Adak"
MY_EMAIL = "adaksudip956@gmail.com"
PORTFOLIO_URL = "https://thebright10.github.io/Portfolio_Sudip/"
RESUME_URL = "https://thebright10.github.io/Portfolio_Sudip/Sudip_Kumar_Adak_Resume.pdf"

# Ensure secrets are available
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")

# Target cities for fresher jobs
TARGET_CITIES = ["Pune, India", "Mumbai, India", "Bangalore, India", "Chennai, India", "Hyderabad, India", "Kolkata, India", "Ahmedabad, India"]
SEARCH_TERM = "Fresher Software Developer"
NUM_JOBS_PER_CITY = 2 # Keep small to avoid rate limits

# Target startups for cold emailing
COLD_EMAIL_TARGETS = [
    {"company": "Razorpay", "hr_email": "jobs@razorpay.com", "location": "Bangalore, India"},
    {"company": "Cred", "hr_email": "careers@cred.club", "location": "Bangalore, India"},
    {"company": "Zerodha", "hr_email": "careers@zerodha.com", "location": "Bangalore, India"},
    {"company": "Postman", "hr_email": "careers@postman.com", "location": "Bangalore, India"},
    {"company": "Swiggy", "hr_email": "careers@swiggy.in", "location": "Pan India"},
    {"company": "Zomato", "hr_email": "careers@zomato.com", "location": "Pan India"},
    {"company": "Groww", "hr_email": "careers@groww.in", "location": "Bangalore, India"},
    {"company": "Pine Labs", "hr_email": "careers@pinelabs.com", "location": "Pune/Mumbai, India"},
    {"company": "Dream11", "hr_email": "careers@dream11.com", "location": "Mumbai, India"}
]

def is_genuine_fresher_job(title, description):
    """Filter out senior roles to ensure genuine fresher/junior jobs."""
    title_lower = title.lower()
    desc_lower = str(description).lower()
    
    # Exclude keywords (extremely strict against experience requirements)
    exclude_words = [
        "senior", "sr", "lead", "manager", "staff", "principal", "director", "head", "architect",
        "5+ years", "4+ years", "3+ years", "2+ years", "1+ years", "1+ year", "2+ year",
        "2 years", "3 years", "4 years", "5 years", "1-3 years", "2-4 years", "3-5 years",
        "minimum 1 year", "minimum 2 year", "experienced", "experience required"
    ]
    for word in exclude_words:
        if word in title_lower or word in desc_lower:
            return False
            
    # Must explicitly mention fresher or entry level to be safe
    include_words = ["fresher", "junior", "jr", "entry level", "entry-level", "0-1 year", "0-2 year", "associate", "intern", "trainee", "graduate", "0 years"]
    if any(word in title_lower for word in include_words):
        return True
        
    # Also check description if title doesn't have it
    if any(word in desc_lower for word in include_words):
        return True
        
    return False

def fetch_jobs():
    import random
    # Pick 2 random cities each run
    cities_to_search = random.sample(TARGET_CITIES, 2)
    jobs_list = []
    
    for city in cities_to_search:
        print(f"Scraping online jobs for '{SEARCH_TERM}' in '{city}'...")
        try:
            jobs_df = scrape_jobs(
                site_name=["indeed", "linkedin"],
                search_term=SEARCH_TERM,
                location=city,
                results_wanted=NUM_JOBS_PER_CITY * 3, # Fetch more to allow filtering
                country_indeed='India'
            )
            
            if not jobs_df.empty:
                for _, row in jobs_df.iterrows():
                    title = row.get('title', '')
                    desc = row.get('description', '')
                    
                    if is_genuine_fresher_job(title, desc):
                        jobs_list.append({
                            "title": title,
                            "company": row.get('company', 'Unknown Company'),
                            "location": row.get('location', city),
                            "url": row.get('job_url', ''),
                            "status": "Apply Online"
                        })
                        
                        if len([j for j in jobs_list if j['location'] == city]) >= NUM_JOBS_PER_CITY:
                            break # Stop if we found enough for this city
                            
        except Exception as e:
            print(f"Error scraping jobs in {city}: {e}")
            
    # Fallback if entirely blocked or no jobs found
    if not jobs_list:
        print("No jobs found via scraper. Using fallback online genuine jobs.")
        jobs_list = [
            {"title": "Junior Software Engineer (Fresher)", "company": "IBM", "location": "Bangalore, Karnataka", "url": "https://www.ibm.com/in-en/employment/", "status": "Apply Online"},
            {"title": "Software Developer Intern", "company": "Amazon", "location": "Hyderabad, Telangana", "url": "https://amazon.jobs", "status": "Apply Online"}
        ]
        
    return jobs_list

def generate_cold_emails():
    """Selects 2 random startups to send a cold application draft to."""
    import random
    targets = random.sample(COLD_EMAIL_TARGETS, 2)
    draft_list = []
    
    for target in targets:
        print(f"Creating cold email draft for startup {target['company']}...")
        status = save_draft_to_gmail(target)
        draft_list.append({
            "title": "Startup Cold Application",
            "company": target['company'],
            "location": target['location'],
            "url": f"mailto:{target['hr_email']}",
            "status": status
        })
        time.sleep(1)
        
    return draft_list

def save_draft_to_gmail(target):
    """
    Connects to Gmail via IMAP and saves a cold cover letter in the Drafts folder.
    """
    subject = f"Application for Software Developer (Fresher) - {MY_NAME}"
    
    body = f"""Dear HR Team at {target['company']},

I am writing to express my strong interest in joining {target['company']} as a Software Developer.

I am currently pursuing my MCA at Pimpri Chinchwad University (PCU) and have completed my BCA from Techno India. I have hands-on experience building full-stack applications like the MindFlow AI Mental Health platform (Python/Django), E-Commerce systems, and Data Analytics dashboards.

Please find my ATS-friendly resume here: {RESUME_URL}
You can also view my full portfolio and projects here: {PORTFOLIO_URL}

I am available for an immediate internship or full-time role and would love to discuss how my skills in Python, Java, SQL, and Web Development can add value to your innovative startup.

Thank you for your time and consideration.

Best regards,
{MY_NAME}
{MY_EMAIL}
"""

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = MY_EMAIL
    msg['To'] = target['hr_email']
    msg.set_content(body)

    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        return "Simulated Draft"
        
    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        drafts_folder = '"[Gmail]/Drafts"'
        date_time = imaplib.Time2Internaldate(time.time())
        mail.append(drafts_folder, '', date_time, str(msg).encode('utf8'))
        mail.logout()
        return "Draft Saved"
    except Exception as e:
        return f"Error: {e}"

def send_daily_digest(jobs):
    """
    Sends an email to Sudip with direct links to apply for today's genuine jobs.
    """
    if not jobs:
        print("No online jobs found to send in digest.")
        return
        
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("⚠️ Credentials missing. Cannot send Daily Digest Email.")
        return
        
    print("Sending Daily Digest Email...")
    
    subject = f"Daily Job Bot Digest: {len(jobs)} Genuine Fresher Jobs Found!"
    
    html_body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333;">
        <h2>Hi Sudip!</h2>
        <p>Your Job Bot found <strong>{len(jobs)} genuine fresher jobs</strong> today. Here are the direct links to apply:</p>
        <table border="1" cellpadding="10" cellspacing="0" style="border-collapse: collapse; width: 100%; max-width: 800px;">
          <tr style="background-color: #f2f2f2;">
            <th>Role</th>
            <th>Company</th>
            <th>Location</th>
            <th>Action</th>
          </tr>
    """
    
    for job in jobs:
        html_body += f"""
          <tr>
            <td>{job['title']}</td>
            <td>{job['company']}</td>
            <td>{job['location']}</td>
            <td><a href="{job['url']}" style="display:inline-block; padding:8px 12px; background-color:#10b981; color:white; text-decoration:none; border-radius:4px;">Apply Online</a></td>
          </tr>
        """
        
    html_body += """
        </table>
        <p style="margin-top: 20px;">Keep applying! Check your <a href="https://thebright10.github.io/Portfolio_Sudip/dashboard.html">Portfolio Dashboard</a> for your complete application history.</p>
        <p>Best,<br>Sudip's Automated Job Bot</p>
      </body>
    </html>
    """
    
    msg = MIMEMultipart("alternative")
    msg['Subject'] = subject
    msg['From'] = MY_EMAIL
    msg['To'] = MY_EMAIL # Send to himself
    
    part = MIMEText(html_body, "html")
    msg.attach(part)
    
    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("✅ Daily Digest Email sent successfully!")
    except Exception as e:
        print(f"❌ Failed to send digest email: {e}")

def update_history(all_items):
    """
    Appends today's jobs to job_history.json.
    """
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    history_file = "job_history.json"
    
    history_data = {}
    if os.path.exists(history_file):
        try:
            with open(history_file, "r") as f:
                history_data = json.load(f)
        except:
            history_data = {}
            
    if "history" not in history_data:
        history_data["history"] = {}
        
    history_data["history"][today_str] = all_items
    history_data["last_updated"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with open(history_file, "w") as f:
        json.dump(history_data, f, indent=4)
        
    print(f"Updated {history_file} successfully.")
    
    # We still keep jobs.json for backward compatibility or simple dashboard stats if needed
    with open('jobs.json', 'w') as f:
        json.dump({
            "last_updated": history_data["last_updated"],
            "total_jobs_today": len([i for i in all_items if i['status'] == 'Apply Online']),
            "total_drafts_saved": len([i for i in all_items if 'Saved' in i['status'] or 'Simulated' in i['status']]),
            "jobs": all_items
        }, f, indent=4)

def main():
    print(f"Starting Daily Job Bot for {MY_NAME}...")
    
    # 1. Fetch genuine online fresher jobs
    online_jobs = fetch_jobs()
    
    # 2. Send email digest of these jobs to Sudip
    send_daily_digest(online_jobs)
    
    # 3. Draft cold emails for Startups
    cold_drafts = generate_cold_emails()
    
    # Combine and save to history
    all_items = online_jobs + cold_drafts
    update_history(all_items)
    
    print("Job Bot execution completed!")

if __name__ == "__main__":
    main()
