"""
Job Search Agent + Auto Resume & Cover Letter Generator
=========================================================
For Piyush Kunjilwar
- Finds top AI/ML jobs daily
- Filters: 0-4 years experience (startups always included)
- For each top 15 jobs: generates tailored resume + cover letter via Claude API
- Emails complete ready-to-paste packages for each role
"""

import requests
import smtplib
import os
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# PIYUSH'S MASTER RESUME — update anytime
# ─────────────────────────────────────────────

MASTER_RESUME = """
Piyush Kunjilwar
Boston, MA | (617) 516-9145 | kunjilwar.p@northeastern.edu
linkedin.com/in/piyush-kunjilwar | github.com/piyush12kunjilwar

EDUCATION
Northeastern University — Boston, MA
Master of Science in Information Systems | Expected May 2026
Coursework: Machine Learning, NLP, Neural Networks, Data Structures & Algorithms
Teaching Assistant: Data Science (Mentored graduate students on ML pipelines and Python)

TECHNICAL SKILLS
Languages: Python, Java, C++, TypeScript, SQL (PostgreSQL), Bash, Scala
Machine Learning: PyTorch (FSDP, DDP), TensorFlow (MirroredStrategy), NCCL, CUDA (Profiling, Streams), Flash Attention, Transformers, ONNX Runtime
Cloud & Infrastructure: AWS (EC2, Lambda, S3, EMR), Docker, Kubernetes, Kafka, Jenkins, GitLab CI/CD
Concepts: Distributed Training (Multi-Node), Agentic Workflows, Model Profiling, RAG, Inference Optimization (Quantization), System Design

PROFESSIONAL EXPERIENCE

CareerGPT — Remote
Applied ML Software Engineer (Co-op) | Jan 2025 – Dec 2025
- Engineered "Deep Research" agentic workflow using Gemini models, orchestrating complex tool-use patterns automating multi-step information retrieval
- Built distributed training infrastructure for SFT and RLHF using PyTorch FSDP across multi-node GPU clusters
- Optimized inter-node coordination by tuning NCCL parameters and implementing gradient accumulation, reducing fine-tuning cost and latency by 40%
- Developed rigorous evaluation pipelines using synthetic data to stress-test model reasoning, identifying and resolving hallucination issues before production

Accenture — India
AI Solutions Developer | Sep 2022 – Aug 2023
- Built real-time event-driven microservices using Kafka and WebSockets for a platform serving 1M+ users
- Optimized consumer group configurations achieving sub-200ms latency with 99.9% system availability
- Collaborated with senior architects to standardize API patterns, accelerating team delivery by 30%

Tata Motors — India
ML Engineering Intern | Jan 2022 – Aug 2022
- Built PySpark pipelines on AWS EMR processing 100GB/day of raw vehicle telemetry for predictive maintenance
- Diagnosed and resolved throughput bottleneck on 1TB+ PostgreSQL cluster, reducing query time by 50%
- Containerized ML inference services using Docker on GCP Compute Engine, reducing inference latency by 32%

KEY PROJECTS

Inference Optimization for NLP (Dream Insight AI)
- Profiled CUDA kernel execution using Nsight Systems, integrating Flash Attention to reduce memory I/O by 40%
- Migrated PyTorch models to ONNX Runtime with 8-bit quantization, achieving 3.5x latency reduction (120ms to 35ms)
- Automated deployment using AWS Spot Instances and Kubernetes HPA

Distributed Rain Prediction System (CNN-RNN Hybrid)
- Engineered DDP training pipeline for ConvLSTM on 2.5M+ satellite image sequences using Mixed Precision (FP16)
- Implemented synchronous ring-allreduce for multi-node gradient synchronization, achieving near-linear scaling
- Built high-throughput tf.data ETL pipeline ensuring 100% GPU utilization during training
"""

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

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
TOP_JOBS_TO_PROCESS = 15  # generate resume+cover letter for top N jobs

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


# ─────────────────────────────────────────────
# FILTERS
# ─────────────────────────────────────────────

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


# ─────────────────────────────────────────────
# ADZUNA SEARCH
# ─────────────────────────────────────────────

def search_adzuna(role, location):
    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")
    if not app_id or not app_key:
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


# ─────────────────────────────────────────────
# SCORING
# ─────────────────────────────────────────────

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


# ─────────────────────────────────────────────
# CLAUDE API — RESUME + COVER LETTER GENERATOR
# ─────────────────────────────────────────────

def generate_resume_and_cover_letter(job):
    """Call Claude API to generate tailored resume + cover letter for a specific job."""
    title   = job.get("title", "N/A")
    company = job.get("company", {}).get("display_name", "N/A")
    desc    = job.get("description", "")[:3000]

    prompt = f"""You are helping Piyush Kunjilwar apply for a job. 

JOB TITLE: {title}
COMPANY: {company}
JOB DESCRIPTION:
{desc}

PIYUSH'S MASTER RESUME:
{MASTER_RESUME}

YOUR TASK — generate TWO things:

1. TAILORED RESUME
Rewrite Piyush's resume specifically for this role. Keep all facts truthful — only reorder, emphasize, and reframe existing experience to match this job's requirements. Use the same sections. Make the summary/skills section lead with what this specific company cares most about. Do not invent new experience.

2. COVER LETTER
Write a complete, human-toned cover letter for this specific role at this specific company. It should:
- Sound like a real person wrote it, not AI
- Open with something specific about this company or role (not generic)
- Connect Piyush's actual experience directly to what this job needs
- Include specific numbers and achievements from his resume
- Be warm, confident, and direct — not corporate or stiff
- End with a natural, non-desperate close
- Be 4-5 paragraphs, not too long

FORMAT YOUR RESPONSE EXACTLY LIKE THIS — use these exact headers:
===RESUME===
[full tailored resume here]

===COVER LETTER===
[full cover letter here]"""

    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": os.getenv("ANTHROPIC_API_KEY", ""),
                "anthropic-version": "2023-06-01"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 3000,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
        full_text = data["content"][0]["text"]

        # parse resume and cover letter
        resume = ""
        cover_letter = ""
        if "===RESUME===" in full_text and "===COVER LETTER===" in full_text:
            parts = full_text.split("===COVER LETTER===")
            resume = parts[0].replace("===RESUME===", "").strip()
            cover_letter = parts[1].strip()
        else:
            resume = full_text[:len(full_text)//2]
            cover_letter = full_text[len(full_text)//2:]

        return resume, cover_letter

    except Exception as e:
        print(f"  Claude API error: {e}")
        return MASTER_RESUME, f"Dear {company} Team,\n\nI am excited to apply for the {title} role..."


# ─────────────────────────────────────────────
# FORMAT EMAIL
# ─────────────────────────────────────────────

def format_job_section(job, rank, resume, cover_letter):
    title    = job.get("title", "N/A")
    company  = job.get("company", {}).get("display_name", "N/A")
    location = job.get("location", {}).get("display_name", "N/A")
    url      = job.get("redirect_url", "#")
    sal_min  = job.get("salary_min")
    sal_max  = job.get("salary_max")
    salary   = "Not listed"
    if sal_min and sal_max: salary = f"${int(sal_min):,} - ${int(sal_max):,}"
    elif sal_max: salary = f"Up to ${int(sal_max):,}"
    created  = job.get("created", "")[:10]
    score    = score_job(job)
    full_text = (title + job.get("description", "")).lower()
    startup_badge = ' <span style="background:#e8f8e8;color:#2e7d32;padding:2px 8px;border-radius:10px;font-size:11px;">Startup</span>' if is_startup_role(full_text) else ""

    # format resume and cover letter as preformatted text
    resume_html = resume.replace("\n", "<br>").replace(" ", "&nbsp;")
    cover_html  = cover_letter.replace("\n", "<br>")

    return f"""
    <div style="border:2px solid #0a66c2;border-radius:12px;padding:20px;margin-bottom:30px;font-family:Arial,sans-serif;">

        <!-- Job Header -->
        <div style="background:#0a66c2;color:white;padding:14px 18px;border-radius:8px;margin-bottom:16px;">
            <h2 style="margin:0;font-size:18px;">#{rank} {title}{startup_badge}</h2>
            <p style="margin:4px 0;opacity:0.9;font-size:14px;">{company} | {location} | {salary} | Posted: {created}</p>
            <p style="margin:4px 0;opacity:0.8;font-size:13px;">Relevance Score: {score}/100</p>
        </div>

        <a href="{url}" style="background:#28a745;color:white;padding:10px 20px;border-radius:6px;
           text-decoration:none;font-size:14px;font-weight:bold;display:inline-block;margin-bottom:20px;">
           Apply Now →
        </a>

        <!-- Cover Letter -->
        <div style="margin-bottom:20px;">
            <div style="background:#fff3cd;padding:10px 14px;border-radius:6px;margin-bottom:10px;">
                <strong>COVER LETTER — Copy and paste this</strong>
            </div>
            <div style="background:#f8f9fa;border:1px solid #dee2e6;border-radius:6px;padding:16px;
                        font-size:14px;line-height:1.7;color:#333;">
                {cover_html}
            </div>
        </div>

        <!-- Resume -->
        <div>
            <div style="background:#e8f4fd;padding:10px 14px;border-radius:6px;margin-bottom:10px;">
                <strong>TAILORED RESUME — Copy and paste this</strong>
            </div>
            <div style="background:#f8f9fa;border:1px solid #dee2e6;border-radius:6px;padding:16px;
                        font-family:monospace;font-size:12px;line-height:1.6;color:#333;white-space:pre-wrap;">
{resume}
            </div>
        </div>

    </div>
    """


def format_email_html(job_sections, filtered_count, total_found):
    today = datetime.now().strftime("%B %d, %Y")
    all_sections = "".join(job_sections)

    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:800px;margin:auto;padding:20px;">

        <div style="background:#0a66c2;color:white;padding:20px;border-radius:8px;margin-bottom:20px;">
            <h1 style="margin:0;">AI/ML Job Digest + Application Kit</h1>
            <p style="margin:4px 0;opacity:0.9;">{today} — Piyush Kunjilwar</p>
            <p style="margin:4px 0;opacity:0.8;font-size:13px;">
                {total_found} jobs found | {filtered_count} over-senior removed |
                {len(job_sections)} application packages ready below
            </p>
        </div>

        <div style="background:#d4edda;border:1px solid #c3e6cb;padding:14px 16px;
                    border-radius:8px;margin-bottom:20px;color:#155724;">
            <strong>How to use this digest:</strong><br>
            1. Scan the job headers — pick your top 3<br>
            2. Click Apply Now for each<br>
            3. Copy-paste the Cover Letter into the application<br>
            4. Copy-paste the Tailored Resume into the application<br>
            5. Done — total time per application: 3 minutes
        </div>

        {all_sections}

        <p style="color:#999;font-size:12px;margin-top:20px;text-align:center;">
            Generated automatically every morning at 8am EST | Job Search Agent by Piyush Kunjilwar
        </p>
    </body></html>
    """


# ─────────────────────────────────────────────
# EMAIL SENDER
# ─────────────────────────────────────────────

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
    msg["Subject"] = f"{job_count} AI/ML Jobs — Resumes + Cover Letters Ready — {today}"
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
        print("Saved to job_digest.html instead")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def run():
    print("Starting Job Search + Application Kit Generator")
    print(f"Searching {len(TARGET_ROLES)} roles x {len(TARGET_LOCATIONS)} locations\n")

    # Step 1 — find jobs
    all_jobs = []
    for role in TARGET_ROLES:
        for location in TARGET_LOCATIONS:
            print(f"  Searching: {role} in {location}")
            jobs = search_adzuna(role, location)
            all_jobs.extend(jobs)
            if jobs: print(f"     Found {len(jobs)} results")

    # Step 2 — filter and rank
    unique_jobs = deduplicate(all_jobs)
    filtered_jobs = [j for j in unique_jobs if should_include(j)]
    removed_count = len(unique_jobs) - len(filtered_jobs)
    scored_jobs = sorted(filtered_jobs, key=score_job, reverse=True)
    top_jobs = scored_jobs[:TOP_JOBS_TO_PROCESS]

    print(f"\nTotal unique: {len(unique_jobs)}")
    print(f"After filtering: {len(filtered_jobs)} ({removed_count} removed)")
    print(f"Generating application kits for top {len(top_jobs)} jobs...\n")

    # Step 3 — generate resume + cover letter for each top job
    job_sections = []
    for i, job in enumerate(top_jobs):
        title   = job.get("title", "N/A")
        company = job.get("company", {}).get("display_name", "N/A")
        print(f"  Generating [{i+1}/{len(top_jobs)}]: {title} at {company}")
        resume, cover_letter = generate_resume_and_cover_letter(job)
        section = format_job_section(job, i+1, resume, cover_letter)
        job_sections.append(section)

    # Step 4 — send email
    html = format_email_html(job_sections, removed_count, len(unique_jobs))
    send_email(html, len(top_jobs))
    print(f"\nDone! {len(top_jobs)} application kits sent to your email.")


if __name__ == "__main__":
    run()
