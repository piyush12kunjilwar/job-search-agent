"""
Job Search Agent for Piyush Kunjilwar
======================================
Filters: 0-4 years experience | Excludes manager/director/senior staff
Exception: Startup roles always included regardless of seniority
"""

import requests
import smtplib
import os
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

TARGET_ROLES = [
    "AI Engineer", "ML Engineer", "Machine Learning Engineer",
    "LLM Engineer", "Applied AI Engineer", "Generative AI Engineer",
    "AI Infrastructure Engineer", "Applied ML Engineer",
]

TARGET_LOCATIONS = [
    "Remote", "Boston, MA", "San Francisco, CA",
    "New York, NY", "Seattle, WA", "Sunnyvale, CA",
]

DAYS_POSTED = 7
MAX_RESULTS = 20
COUNTRY = "us"

SENIOR_PATTERNS = [
    "manager", "director", "vp ", "vice president", "head of",
    "chief", "principal scientist", "principal engineer",
    "staff engineer", "distinguished engineer", "senior staff",
    "senior director", "senior manager", "lead scientist",
    "engineering manager", "research manager", "science manager",
    "senior applied scientist", "senior research scientist",
]

EXPERIENCE_PATTERNS = [
    "8+ years", "9+ years", "10+ years", "12+ years",
    "15+ years", "7+ years experience",
]

STARTUP_SIGNALS = [
    "startup", "early stage", "seed stage", "series a", "series b",
    "founding engineer", "founding member", "stealth", "pre-ipo",
    "yc ", "y combinator", "techstars", "venture", "early-stage",
    "0 to 1", "0-to-1",
]


def is_startup_role(text):
    return any(s in text for s in STARTUP_SIGNALS)


def is_too_senior(text):
    return any(p in text for p in SENIOR_PATTERNS) or any(p in text for p in EXPERIENCE_PATTERNS)


def should_include(job):
    title = job.get("title", "").lower()
    desc = job.get("description", "").lower()
    company = job.get("company", {}).get("display_name", "").lower()
    full_text = f"{title} {desc} {company}"
    if is_startup_role(full_text):
        return True
    if is_too_senior(full_text):
        return False
    return True


def search_adzuna(role, location):
    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        print("No Adzuna credentials found")
        return []
    base_url = f"https://api.adzuna.com/v1/api/jobs/{COUNTRY}/search/1"
    loc = "" if location.lower() == "remote" else location.split(",")[0].strip()
    what = role if location.lower() != "remote" else f"{role} remote"
    params = {
        "app_id": app_id, "app_key": app_key,
        "results_per_page": MAX_RESULTS, "what": what,
        "where": loc, "max_days_old": DAYS_POSTED,
        "content-type": "application/json", "sort_by": "date",
    }
    try:
        resp = requests.get(base_url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("results", [])
    except Exception as e:
        print(f"  Error: {e}")
        return []


def generate_linkedin_urls():
    base = "https://www.linkedin.com/jobs/search/?"
    locations = {
        "Remote (USA)": "103644278", "Boston MA": "100506914",
        "San Francisco": "102277331", "New York": "102571732", "Seattle": "103644278",
    }
    urls = []
    for role in TARGET_ROLES[:5]:
        for loc_name, geo_id in locations.items():
            remote_filter = "&f_WT=2" if "Remote" in loc_name else ""
            url = (f"{base}keywords={requests.utils.quote(role)}&geoId={geo_id}"
                   f"&f_TPR=r604800&f_E=1%2C2%2C3{remote_filter}&sortBy=DD")
            urls.append({"role": role, "location": loc_name, "url": url})
    return urls


def score_job(job):
    score = 0
    title = (job.get("title", "") + " " + job.get("description", "")).lower()
    high_value = ["pytorch", "llm", "rlhf", "fsdp", "agentic", "distributed training",
                  "inference", "generative ai", "foundation model", "transformers",
                  "fine-tuning", "mlops", "cuda", "gpu"]
    medium_value = ["machine learning", "deep learning", "nlp", "python", "tensorflow",
                    "kubernetes", "docker", "aws", "gcp", "neural network", "model training"]
    hard_negative = ["computer vision only", "ros ", "embedded systems", "fpga", "robotics perception"]
    for kw in high_value:
        if kw in title: score += 15
    for kw in medium_value:
        if kw in title: score += 5
    for kw in hard_negative:
        if kw in title: score -= 25
    if is_startup_role(title): score += 15
    salary_max = job.get("salary_max", 0) or 0
    if salary_max > 200000: score += 20
    elif salary_max > 150000: score += 10
    elif salary_max > 120000: score += 5
    created = job.get("created", "")
    if created:
        try:
            posted_date = datetime.fromisoformat(created.replace("Z", "+00:00"))
            days_ago = (datetime.now().astimezone() - posted_date).days
            if days_ago <= 2: score += 15
            elif days_ago <= 5: score += 8
        except: pass
    return max(0, min(100, score))


def deduplicate(jobs):
    seen = set()
    unique = []
    for job in jobs:
        key = f"{job.get('title','').lower()}_{job.get('company', {}).get('display_name','').lower()}"
        if key not in seen:
            seen.add(key)
            unique.append(job)
    return unique


def format_job_html(job, rank):
    title    = job.get("title", "N/A")
    company  = job.get("company", {}).get("display_name", "N/A")
    location = job.get("location", {}).get("display_name", "N/A")
    url      = job.get("redirect_url", "#")
    desc     = job.get("description", "")[:300] + "..."
    sal_min  = job.get("salary_min")
    sal_max  = job.get("salary_max")
    salary   = "Not listed"
    if sal_min and sal_max: salary = f"${int(sal_min):,} - ${int(sal_max):,}"
    elif sal_max: salary = f"Up to ${int(sal_max):,}"
    created  = job.get("created", "")[:10]
    score    = score_job(job)
    full_text = (title + job.get("description", "")).lower()
    startup_badge = ' <span style="background:#e8f8e8;color:#2e7d32;padding:2px 8px;border-radius:10px;font-size:11px;">Startup</span>' if is_startup_role(full_text) else ""
    return f"""
    <div style="border:1px solid #e0e0e0;border-radius:8px;padding:16px;margin-bottom:16px;font-family:Arial,sans-serif;">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;">
            <h3 style="margin:0;color:#0a66c2;">#{rank} {title}{startup_badge}</h3>
            <span style="background:#e8f4fd;color:#0a66c2;padding:4px 10px;border-radius:20px;font-size:12px;">Score: {score}/100</span>
        </div>
        <p style="margin:6px 0;color:#333;"><strong>Company:</strong> {company}</p>
        <p style="margin:6px 0;color:#333;"><strong>Location:</strong> {location}</p>
        <p style="margin:6px 0;color:#333;"><strong>Salary:</strong> {salary}</p>
        <p style="margin:6px 0;color:#333;"><strong>Posted:</strong> {created}</p>
        <p style="margin:8px 0;color:#555;font-size:13px;">{desc}</p>
        <a href="{url}" style="background:#0a66c2;color:white;padding:8px 16px;border-radius:4px;text-decoration:none;font-size:13px;display:inline-block;margin-top:8px;">Apply Now</a>
    </div>"""


def format_email_html(jobs, linkedin_urls, filtered_count):
    today = datetime.now().strftime("%B %d, %Y")
    job_cards = "".join(format_job_html(j, i+1) for i, j in enumerate(jobs[:15]))
    linkedin_links = "".join(f'<li><a href="{u["url"]}">{u["role"]} - {u["location"]}</a></li>' for u in linkedin_urls[:10])
    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:700px;margin:auto;padding:20px;">
        <div style="background:#0a66c2;color:white;padding:20px;border-radius:8px;margin-bottom:20px;">
            <h1 style="margin:0;">AI/ML Job Digest</h1>
            <p style="margin:4px 0;opacity:0.9;">{today} - Curated for Piyush Kunjilwar</p>
        </div>
        <div style="background:#f0f7ff;padding:12px 16px;border-radius:8px;margin-bottom:20px;">
            <strong>Targeting:</strong> 0-4 years experience | Remote USA + Boston + SF + NYC<br>
            <strong>Filter applied:</strong> {filtered_count} manager/director/senior staff roles removed | Startups always included
        </div>
        <h2>Top Matched Jobs ({len(jobs[:15])} found)</h2>
        {job_cards}
        <h2>LinkedIn Quick Search Links</h2>
        <ul>{linkedin_links}</ul>
        <div style="background:#fff3cd;padding:12px 16px;border-radius:8px;margin-top:20px;">
            <strong>Today's Action:</strong> Apply to top 3 + message hiring manager on LinkedIn.
        </div>
    </body></html>"""


def send_email(html_content, job_count):
    sender    = os.getenv("EMAIL_SENDER")
    password  = os.getenv("EMAIL_PASSWORD")
    recipient = os.getenv("EMAIL_RECIPIENT", "kunjilwar.p@northeastern.edu")
    if not sender or not password:
        with open("job_digest.html", "w") as f: f.write(html_content)
        print("Saved to job_digest.html")
        return
    today = datetime.now().strftime("%b %d")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"{job_count} AI/ML Jobs (0-4yr level) - {today}"
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(html_content, "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, recipient, msg.as_string())
        print(f"Email sent to {recipient}")
    except Exception as e:
        print(f"Email failed: {e}")
        with open("job_digest.html", "w") as f: f.write(html_content)


def run():
    print("Starting Job Search Agent for Piyush Kunjilwar")
    print(f"Searching {len(TARGET_ROLES)} roles x {len(TARGET_LOCATIONS)} locations")
    print(f"Filter: last {DAYS_POSTED} days | 0-4 years experience level\n")
    all_jobs = []
    for role in TARGET_ROLES:
        for location in TARGET_LOCATIONS:
            print(f"  Searching: {role} in {location}")
            jobs = search_adzuna(role, location)
            all_jobs.extend(jobs)
            if jobs: print(f"     Found {len(jobs)} results")
    unique_jobs = deduplicate(all_jobs)
    print(f"\nTotal unique jobs before filtering: {len(unique_jobs)}")
    filtered_jobs = [j for j in unique_jobs if should_include(j)]
    removed_count = len(unique_jobs) - len(filtered_jobs)
    print(f"Removed {removed_count} manager/senior/director roles")
    print(f"Jobs remaining: {len(filtered_jobs)}")
    scored_jobs = sorted(filtered_jobs, key=score_job, reverse=True)
    linkedin_urls = generate_linkedin_urls()
    html = format_email_html(scored_jobs, linkedin_urls, removed_count)
    send_email(html, len(scored_jobs[:15]))
    print("\nTOP 5 JOBS:")
    print("=" * 60)
    for i, job in enumerate(scored_jobs[:5]):
        title   = job.get("title", "N/A")
        company = job.get("company", {}).get("display_name", "N/A")
        loc     = job.get("location", {}).get("display_name", "N/A")
        score   = score_job(job)
        url     = job.get("redirect_url", "N/A")
        startup = "STARTUP" if is_startup_role((title + job.get("description","")).lower()) else ""
        print(f"#{i+1} [{score}/100] {title} {startup}")
        print(f"    {company} | {loc}")
        print(f"    {url}\n")
    print("Done! Check your email.")

if __name__ == "__main__":
    run()
