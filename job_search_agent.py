"""
Job Search Agent for Piyush Kunjilwar
======================================
Searches for AI/ML Engineer roles across the USA (Remote + Boston + SF + NYC)
Uses Adzuna API (free tier: 250 calls/month) + LinkedIn search URLs
Sends results via email digest

Setup Instructions:
1. Get free Adzuna API key at: https://developer.adzuna.com/
2. pip install requests python-dotenv
3. Create a .env file with your credentials (see below)
4. Run: python job_search_agent.py
5. For daily automation: add to cron or GitHub Actions

.env file format:
-----------------
ADZUNA_APP_ID=your_app_id
ADZUNA_APP_KEY=your_app_key
EMAIL_SENDER=your_gmail@gmail.com
EMAIL_PASSWORD=your_gmail_app_password
EMAIL_RECIPIENT=kunjilwar.p@northeastern.edu
"""

import requests
import json
import smtplib
import os
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# YOUR TARGET CONFIGURATION — edit freely
# ─────────────────────────────────────────────

TARGET_ROLES = [
    "AI Engineer",
    "ML Engineer",
    "Machine Learning Engineer",
    "LLM Engineer",
    "Applied AI Engineer",
    "Generative AI Engineer",
    "AI Infrastructure Engineer",
    "Applied ML Engineer",
]

TARGET_LOCATIONS = [
    "Remote",           # searches remote USA
    "Boston, MA",
    "San Francisco, CA",
    "New York, NY",
    "Seattle, WA",
    "Sunnyvale, CA",
]

KEYWORDS_MUST_HAVE = [
    "PyTorch", "LLM", "agentic", "distributed training",
    "RLHF", "inference", "generative AI", "foundation model"
]

KEYWORDS_EXCLUDE = [
    "computer vision only", "robotics only", "embedded only",
    "10+ years", "15+ years", "senior staff", "principal"
]

DAYS_POSTED = 7          # only jobs posted in last 7 days
MAX_RESULTS = 20         # results per search query
COUNTRY = "us"           # Adzuna country code


# ─────────────────────────────────────────────
# ADZUNA API SEARCH
# ─────────────────────────────────────────────

def search_adzuna(role: str, location: str) -> list:
    """Search Adzuna for a specific role + location."""
    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")

    if not app_id or not app_key:
        print("⚠️  Adzuna credentials not found in .env — skipping API search")
        return []

    base_url = f"https://api.adzuna.com/v1/api/jobs/{COUNTRY}/search/1"
    
    # build location param
    loc = "" if location.lower() == "remote" else location.split(",")[0].strip()
    what = role if location.lower() != "remote" else f"{role} remote"

    params = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": MAX_RESULTS,
        "what": what,
        "where": loc,
        "max_days_old": DAYS_POSTED,
        "content-type": "application/json",
        "sort_by": "date",
    }

    try:
        resp = requests.get(base_url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        jobs = data.get("results", [])
        return jobs
    except Exception as e:
        print(f"  Adzuna error for '{role}' in '{location}': {e}")
        return []


# ─────────────────────────────────────────────
# LINKEDIN SEARCH URL GENERATOR
# ─────────────────────────────────────────────

def generate_linkedin_urls() -> list:
    """
    Generates LinkedIn job search URLs for your target roles.
    These open directly in browser — no API key needed.
    """
    base = "https://www.linkedin.com/jobs/search/?"
    
    # LinkedIn location GeoIDs
    locations = {
        "Remote (USA)": "103644278",   # United States + remote filter
        "Boston MA":    "100506914",
        "San Francisco": "102277331",
        "New York":     "102571732",
        "Seattle":      "103644278",
    }

    urls = []
    for role in TARGET_ROLES[:5]:  # top 5 roles
        for loc_name, geo_id in locations.items():
            remote_filter = "&f_WT=2" if "Remote" in loc_name else ""
            url = (
                f"{base}"
                f"keywords={requests.utils.quote(role)}"
                f"&geoId={geo_id}"
                f"&f_TPR=r604800"  # posted last 7 days
                f"&f_E=1%2C2%2C3"  # entry to mid level
                f"{remote_filter}"
                f"&sortBy=DD"       # sort by date
            )
            urls.append({
                "role": role,
                "location": loc_name,
                "url": url
            })
    return urls


# ─────────────────────────────────────────────
# JOB RELEVANCE SCORER
# ─────────────────────────────────────────────

def score_job(job: dict) -> int:
    """
    Score a job 0-100 based on relevance to Piyush's profile.
    Higher = better match.
    """
    score = 0
    
    title = (job.get("title", "") + " " + job.get("description", "")).lower()
    
    # high value keywords
    high_value = ["pytorch", "llm", "rlhf", "fsdp", "agentic", 
                  "distributed training", "inference", "generative ai",
                  "foundation model", "transformers", "fine-tuning",
                  "mlops", "cuda", "gpu"]
    
    medium_value = ["machine learning", "deep learning", "nlp", "python",
                    "tensorflow", "kubernetes", "docker", "aws", "gcp",
                    "neural network", "model training"]
    
    negative = ["10+ years", "15+ years", "principal", "staff engineer",
                "computer vision only", "ros", "embedded", "fpga",
                "robotics perception"]
    
    for kw in high_value:
        if kw in title:
            score += 15
    
    for kw in medium_value:
        if kw in title:
            score += 5
    
    for kw in negative:
        if kw in title:
            score -= 20
    
    # salary bonus
    salary_max = job.get("salary_max", 0) or 0
    if salary_max > 200000:
        score += 20
    elif salary_max > 150000:
        score += 10
    elif salary_max > 120000:
        score += 5

    # recency bonus
    created = job.get("created", "")
    if created:
        try:
            posted_date = datetime.fromisoformat(created.replace("Z", "+00:00"))
            days_ago = (datetime.now().astimezone() - posted_date).days
            if days_ago <= 2:
                score += 15
            elif days_ago <= 5:
                score += 8
        except:
            pass
    
    return max(0, min(100, score))


# ─────────────────────────────────────────────
# DEDUPLICATE JOBS
# ─────────────────────────────────────────────

def deduplicate(jobs: list) -> list:
    """Remove duplicate jobs by title + company."""
    seen = set()
    unique = []
    for job in jobs:
        key = f"{job.get('title','').lower()}_{job.get('company', {}).get('display_name','').lower()}"
        if key not in seen:
            seen.add(key)
            unique.append(job)
    return unique


# ─────────────────────────────────────────────
# FORMAT JOBS FOR EMAIL
# ─────────────────────────────────────────────

def format_job_html(job: dict, rank: int) -> str:
    title    = job.get("title", "N/A")
    company  = job.get("company", {}).get("display_name", "N/A")
    location = job.get("location", {}).get("display_name", "N/A")
    url      = job.get("redirect_url", "#")
    desc     = job.get("description", "")[:300] + "..."
    
    sal_min  = job.get("salary_min")
    sal_max  = job.get("salary_max")
    salary   = "Not listed"
    if sal_min and sal_max:
        salary = f"${int(sal_min):,} – ${int(sal_max):,}"
    elif sal_max:
        salary = f"Up to ${int(sal_max):,}"
    
    created  = job.get("created", "")[:10]
    score    = score_job(job)

    return f"""
    <div style="border:1px solid #e0e0e0; border-radius:8px; padding:16px; margin-bottom:16px; font-family:Arial,sans-serif;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <h3 style="margin:0; color:#0a66c2;">#{rank} {title}</h3>
            <span style="background:#e8f4fd; color:#0a66c2; padding:4px 10px; border-radius:20px; font-size:12px;">
                Score: {score}/100
            </span>
        </div>
        <p style="margin:6px 0; color:#333;"><strong>🏢 Company:</strong> {company}</p>
        <p style="margin:6px 0; color:#333;"><strong>📍 Location:</strong> {location}</p>
        <p style="margin:6px 0; color:#333;"><strong>💰 Salary:</strong> {salary}</p>
        <p style="margin:6px 0; color:#333;"><strong>📅 Posted:</strong> {created}</p>
        <p style="margin:8px 0; color:#555; font-size:13px;">{desc}</p>
        <a href="{url}" style="background:#0a66c2; color:white; padding:8px 16px; border-radius:4px; 
           text-decoration:none; font-size:13px; display:inline-block; margin-top:8px;">
           Apply Now →
        </a>
    </div>
    """


def format_email_html(jobs: list, linkedin_urls: list) -> str:
    today = datetime.now().strftime("%B %d, %Y")
    job_cards = "".join(format_job_html(j, i+1) for i, j in enumerate(jobs[:15]))
    
    linkedin_links = "".join(
        f'<li><a href="{u["url"]}">{u["role"]} — {u["location"]}</a></li>'
        for u in linkedin_urls[:10]
    )

    return f"""
    <html><body style="font-family:Arial,sans-serif; max-width:700px; margin:auto; padding:20px;">
        <div style="background:#0a66c2; color:white; padding:20px; border-radius:8px; margin-bottom:20px;">
            <h1 style="margin:0;">🤖 AI/ML Job Digest</h1>
            <p style="margin:4px 0; opacity:0.9;">{today} — Curated for Piyush Kunjilwar</p>
        </div>
        
        <div style="background:#f0f7ff; padding:12px 16px; border-radius:8px; margin-bottom:20px;">
            <strong>Your Profile:</strong> AI/ML Engineer | PyTorch FSDP | RLHF | Agentic Systems | 
            Distributed Training | Inference Optimization<br>
            <strong>Targeting:</strong> Remote (USA) + Boston + SF + NYC | Posted last 7 days
        </div>

        <h2>🎯 Top Matched Jobs ({len(jobs[:15])} found)</h2>
        {job_cards}
        
        <h2>🔗 LinkedIn Quick Search Links</h2>
        <p style="color:#555;">Click to search directly on LinkedIn — already filtered for your roles:</p>
        <ul>{linkedin_links}</ul>
        
        <div style="background:#fff3cd; padding:12px 16px; border-radius:8px; margin-top:20px;">
            <strong>💡 Today's Action:</strong> Apply to top 3 scored jobs + send LinkedIn message 
            to hiring manager using your proven outreach templates.
        </div>
        
        <p style="color:#999; font-size:12px; margin-top:20px;">
            Generated by your personal Job Search Agent | Run again anytime: python job_search_agent.py
        </p>
    </body></html>
    """


# ─────────────────────────────────────────────
# EMAIL SENDER
# ─────────────────────────────────────────────

def send_email(html_content: str, job_count: int):
    """Send digest via Gmail. Requires Gmail App Password."""
    sender   = os.getenv("EMAIL_SENDER")
    password = os.getenv("EMAIL_PASSWORD")
    recipient = os.getenv("EMAIL_RECIPIENT", "kunjilwar.p@northeastern.edu")

    if not sender or not password:
        print("\n⚠️  Email credentials not set — saving HTML digest to file instead")
        with open("job_digest.html", "w") as f:
            f.write(html_content)
        print("✅ Saved to job_digest.html — open in your browser!")
        return

    today = datetime.now().strftime("%b %d")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🤖 {job_count} AI/ML Jobs Found — {today}"
    msg["From"]    = sender
    msg["To"]      = recipient
    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, recipient, msg.as_string())
        print(f"✅ Email sent to {recipient}")
    except Exception as e:
        print(f"❌ Email failed: {e}")
        print("💡 Saving to job_digest.html instead")
        with open("job_digest.html", "w") as f:
            f.write(html_content)


# ─────────────────────────────────────────────
# MAIN RUNNER
# ─────────────────────────────────────────────

def run():
    print("🚀 Starting Job Search Agent for Piyush Kunjilwar")
    print(f"   Searching {len(TARGET_ROLES)} roles × {len(TARGET_LOCATIONS)} locations")
    print(f"   Filter: posted last {DAYS_POSTED} days\n")

    all_jobs = []

    # search Adzuna
    for role in TARGET_ROLES:
        for location in TARGET_LOCATIONS:
            print(f"  🔍 Searching: {role} in {location}")
            jobs = search_adzuna(role, location)
            all_jobs.extend(jobs)
            if jobs:
                print(f"     Found {len(jobs)} results")

    # deduplicate + score + sort
    unique_jobs = deduplicate(all_jobs)
    scored_jobs = sorted(unique_jobs, key=score_job, reverse=True)
    
    print(f"\n✅ Total unique jobs found: {len(unique_jobs)}")
    print(f"✅ Top scored jobs to send: {min(15, len(scored_jobs))}\n")

    # generate linkedin urls
    linkedin_urls = generate_linkedin_urls()

    # if no Adzuna jobs (no API key yet), still send LinkedIn links
    if not scored_jobs:
        print("ℹ️  No Adzuna jobs found — sending LinkedIn search links only")
        print("   Get your free Adzuna API key at: https://developer.adzuna.com/\n")

    # format + send
    html = format_email_html(scored_jobs, linkedin_urls)
    send_email(html, len(scored_jobs[:15]))

    # also print top 5 to terminal
    print("\n🏆 TOP 5 JOBS BY RELEVANCE SCORE:")
    print("=" * 60)
    for i, job in enumerate(scored_jobs[:5]):
        title   = job.get("title", "N/A")
        company = job.get("company", {}).get("display_name", "N/A")
        loc     = job.get("location", {}).get("display_name", "N/A")
        score   = score_job(job)
        url     = job.get("redirect_url", "N/A")
        print(f"\n#{i+1} [{score}/100] {title}")
        print(f"    {company} | {loc}")
        print(f"    {url}")

    print("\n✅ Done! Check your email or open job_digest.html")


if __name__ == "__main__":
    run()
