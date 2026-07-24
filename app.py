import os
import json
import logging
from flask import Flask, request, jsonify, render_template
import google.generativeai as genai
from PyPDF2 import PdfReader
from jobspy import scrape_jobs

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configure Gemini API
# You must set the GEMINI_API_KEY environment variable before running.
genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))

def extract_text_from_pdf(pdf_file):
    reader = PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

def analyze_resume_with_ai(resume_text):
    """Uses Gemini to extract job search keywords and resume feedback."""
    try:
        model = genai.GenerativeModel('gemini-pro')
        prompt = f"""
        You are an expert tech recruiter and ATS system.
        Read the following resume text and provide exactly two things in valid JSON format:
        1. "search_terms": An array of 2 or 3 highly specific job titles to search for based on their skills and experience level (e.g., ["Python Developer Fresher", "Junior Data Analyst"]).
        2. "suggestions": An array of 2 or 3 short, actionable bullet points on how they can improve this resume for ATS systems.
        
        Resume text:
        {resume_text[:4000]} # Limit text to avoid token limits
        
        Return ONLY valid JSON.
        """
        response = model.generate_content(prompt)
        # Strip out markdown formatting if present
        result_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(result_text)
    except Exception as e:
        logger.error(f"Error calling Gemini AI: {e}")
        return {
            "search_terms": ["Software Developer", "Data Analyst"],
            "suggestions": ["Ensure your contact information is clearly visible at the top.", "Use strong action verbs to describe your projects."]
        }

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/analyze', methods=['POST'])
def analyze_resume():
    if 'resume' not in request.files:
        return jsonify({"error": "No resume file provided"}), 400
        
    file = request.files['resume']
    if file.filename == '':
        return jsonify({"error": "Empty filename"}), 400
        
    try:
        # 1. Extract text
        resume_text = extract_text_from_pdf(file)
        if not resume_text.strip():
            return jsonify({"error": "Could not extract text from PDF. It may be an image-based PDF."}), 400
            
        # 2. Analyze with Gemini
        ai_analysis = analyze_resume_with_ai(resume_text)
        
        return jsonify({
            "success": True,
            "data": ai_analysis
        })
    except Exception as e:
        logger.error(f"Error processing resume: {e}")
        return jsonify({"error": "Failed to process resume"}), 500

@app.route('/api/search', methods=['POST'])
def search_jobs():
    data = request.json
    if not data or 'search_terms' not in data:
        return jsonify({"error": "search_terms required"}), 400
        
    search_terms = data['search_terms']
    location = data.get('location', "India")
    
    all_jobs = []
    
    try:
        # Search for each term
        for term in search_terms:
            logger.info(f"Searching for '{term}' in '{location}'...")
            jobs_df = scrape_jobs(
                site_name=["indeed", "linkedin"],
                search_term=term,
                location=location,
                results_wanted=5,
                country_indeed='India' if "India" in location else None
            )
            
            if not jobs_df.empty:
                for _, row in jobs_df.iterrows():
                    all_jobs.append({
                        "title": row.get('title', 'Unknown'),
                        "company": row.get('company', 'Unknown'),
                        "location": row.get('location', location),
                        "url": row.get('job_url', '#'),
                        "source": term
                    })
                    
        return jsonify({
            "success": True,
            "jobs": all_jobs
        })
    except Exception as e:
        logger.error(f"Error scraping jobs: {e}")
        return jsonify({"error": "Failed to scrape jobs due to rate limits or network issues."}), 500

if __name__ == '__main__':
    # Ensure templates folder exists
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    app.run(debug=True, port=5000)
