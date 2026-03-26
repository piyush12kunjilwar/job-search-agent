"""
Job Search Agent — Multi-Source + Resume & Cover Letter Generator
==================================================================
Sources: Adzuna API, Indeed RSS, Remotive API, Wellfound, YC Jobs, The Muse API
Filters: 0-4 years experience | Startups always included
Generates: Tailored resume + cover letter for top 15 jobs via Claude API
"""

import requests
import smtplib
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv
from urllib.parse import quote

load_dotenv()

# ─────────────────────────────────────────────
# PIYUSH'S MASTER RESUME
# ─────────────────────────────────────────────

MASTER_RESUME = """Piyush Kunjilwar
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
Applied ML Software Engineer (Co-op) | Jan 2025 - Dec 2025
- Engineered Deep Research agentic workflow using Gemini models, orchestrating complex tool-use patterns automating multi-step information retrieval
- Built distributed training infrastructure for SFT and RLHF using PyTorch FSDP across multi-node GPU clusters
- Optimized inter-node coordination by tuning NCCL parameters and implementing gradient accumulation, reducing fine-tuning cost and latency by 40%
- Developed rigorous evaluation pipelines using synthetic data to stress-test model reasoning, identifying hallucination issues before production

Accenture — India
AI Solutions Developer | Sep 2022 - Aug 2023
- Built real-time event-driven microservices using Kafka and WebSockets for a platform serving 1M+ users
- Optimized consumer group configurations achieving sub-200ms latency with 99.9% system availability
- Collaborated with senior architects to standardize API patterns, accelerating team delivery by 30%

Tata Motors — India
ML Engineering Intern | Jan 2022 - Aug 2022
- Built PySpark pipelines on AWS EMR processing 100GB/day of raw vehicle telemetry for predictive maintenance
- Diagnosed and resolved throughput bottleneck on 1TB+ PostgreSQL cluster, reducing query time by 50%
- Containerized ML inference services using Docker on GCP Compute Engine, reducing inference latency by 32%

KEY PROJECTS

Inference Optimization for NLP (Dream Insight AI)
- Profiled CUDA kernel execution using Nsight Systems, integrating Flash Attention to reduce memory I/O by 40%
- Migrated PyTorch models to ONNX Runtime with 8-bit quantization, achieving 3.5x latency reduction (120ms to 35ms)
- Automated deployment using AWS Spot Instances and Kubernetes HPA

Distributed Rain Prediction System (CNN-RNN Hybrid)
- Engineered DDP training pipeline for ConvLSTM on 2.5M+ satellite image sequences using Mixed Precision FP16
- Implemented synchronous ring-allreduce for multi-node gradient synchronization achieving near-linear scaling
- Built high-throughput tf.data ETL pipeline ensuring 100% GPU utilization during training"""

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

TARGET_ROLES = [
    "AI Engineer", "ML Engineer", "Machine Learning Engineer",
    "LLM Engineer", "Applied AI Engineer", "Generative AI Engineer",
    "AI Infrastructure Engineer", "Applied ML Engineer",
]

TARGET_KEYWORDS = [
    "AI Engineer", "ML Engineer", "LLM Engineer",
    "Machine Learning Engineer", "Generative AI Engineer",
    "Applied AI", "AI Infrastructure",
]

TARGET_LOCATIONS = [
    "Remote", "Boston, MA", "San Francisco, CA",
    "New York, NY", "Seattle, WA", "Sunnyvale, CA",
]

DAYS_POSTED = 7
MAX_RESULTS = 20
COUNTRY = "us"
TOP_JOBS_TO_PROCESS = 15

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

HIGH_VALUE_KEYWORDS = [
    "pytorch", "llm", "rlhf", "fsdp", "agentic", "distributed training",
    "inference", "generative ai", "foundation model", "transformers",
    "fine-tuning", "mlops", "cuda", "gpu", "onnx", "ray", "vllm",
]


# ─────────────────────────────────────────────
# FILTERS + SCORING
# ─────────────────────────────────────────────

def is_startup_role(text):
    return any(s in text.lower() for s in STARTUP_SIGNALS)

def is_too_senior(text):
    t = text.lower()
    return any(p in t for p in SENIOR_PATTERNS) or any(p in t for p in EXPERIENCE_PATTERNS)

def should_include(job):
    title = job.get("title", "").lower()
    desc = job.get("description", "").lower()
    company = job.get("company", "").lower()
    full_text = f"{title} {desc} {company}"
    if is_startup_role(full_text):
        return True
    if is_too_senior(full_text):
        return False
    return True

def score_job(job):
    score = 0
    text = (job.get("title", "") + " " + job.get("description", "")).lower()
    medium_value = ["machine learning", "deep learning", "nlp", "python",
                    "tensorflow", "kubernetes", "docker", "aws", "gcp"]
    hard_negative = ["computer vision only", "ros ", "embedded systems",
                     "fpga", "robotics perception", "self-driving only"]
    for kw in HIGH_VALUE_KEYWORDS:
        if kw in text: score += 15
    for kw in medium_value:
        if kw in text: score += 5
    for kw in hard_negative:
        if kw in text: score -= 25
    if is_startup_role(text): score += 15
    salary_max = job.get("salary_max", 0) or 0
    if salary_max > 200000: score += 20
    elif salary_max > 150000: score += 10
    elif salary_max > 120000: score += 5
    created = job.get("date_posted", "")
    if created:
        try:
            if "T" in created:
                posted_date = datetime.fromisoformat(created.replace("Z", "+00:00"))
            else:
                posted_date = datetime.strptime(created, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            days_ago = (datetime.now(timezone.utc) - posted_date).days
            if days_ago <= 2: score += 15
            elif days_ago <= 5: score += 8
        except: pass
    return max(0, min(100, score))

def deduplicate(jobs):
    seen = set()
    unique = []
    for job in jobs:
        key = f"{job.get('title','').lower().strip()}_{job.get('company','').lower().strip()}"
        if key not in seen:
            seen.add(key)
            unique.append(job)
    return unique

def normalize_job(title, company, location, description, url, date_posted, source, salary_min=0, salary_max=0):
    """Normalize all job sources into a single dict format."""
    return {
        "title": title,
        "company": company,
        "location": location,
        "description": description,
        "url": url,
        "date_posted": date_posted,
        "source": source,
        "salary_min": salary_min,
        "salary_max": salary_max,
    }


# ─────────────────────────────────────────────
# SOURCE 1 — ADZUNA API
# ─────────────────────────────────────────────

def search_adzuna():
    print("\n[1/6] Searching Adzuna API...")
    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        print("  No Adzuna credentials — skipping")
        return []
    jobs = []
    for role in TARGET_ROLES:
        for location in TARGET_LOCATIONS:
            loc = "" if location.lower() == "remote" else location.split(",")[0].strip()
            what = role if location.lower() != "remote" else f"{role} remote"
            params = {
                "app_id": app_id, "app_key": app_key,
                "results_per_page": MAX_RESULTS, "what": what,
                "where": loc, "max_days_old": DAYS_POSTED,
                "content-type": "application/json", "sort_by": "date",
            }
            try:
                resp = requests.get(
                    f"https://api.adzuna.com/v1/api/jobs/{COUNTRY}/search/1",
                    params=params, timeout=10
                )
                resp.raise_for_status()
                for j in resp.json().get("results", []):
                    sal_min = j.get("salary_min", 0) or 0
                    sal_max = j.get("salary_max", 0) or 0
                    created = j.get("created", "")[:10]
                    jobs.append(normalize_job(
                        title=j.get("title", ""),
                        company=j.get("company", {}).get("display_name", ""),
                        location=j.get("location", {}).get("display_name", ""),
                        description=j.get("description", ""),
                        url=j.get("redirect_url", ""),
                        date_posted=created,
                        source="Adzuna",
                        salary_min=sal_min,
                        salary_max=sal_max,
                    ))
            except Exception as e:
                print(f"  Adzuna error: {e}")
    print(f"  Found {len(jobs)} jobs from Adzuna")
    return jobs


# ─────────────────────────────────────────────
# SOURCE 2 — INDEED RSS FEEDS
# ─────────────────────────────────────────────

def search_indeed():
    print("\n[2/6] Searching Indeed RSS feeds...")
    jobs = []
    queries = [
        "AI+Engineer", "ML+Engineer", "LLM+Engineer",
        "Machine+Learning+Engineer", "Generative+AI+Engineer", "Applied+AI+Engineer",
    ]
    locations = ["remote", "Boston%2C+MA", "San+Francisco%2C+CA", "New+York%2C+NY"]

    for query in queries:
        for loc in locations:
            url = f"https://www.indeed.com/rss?q={query}&l={loc}&fromage={DAYS_POSTED}&sort=date"
            try:
                headers = {"User-Agent": "Mozilla/5.0 (compatible; JobSearchBot/1.0)"}
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code != 200:
                    continue
                root = ET.fromstring(resp.content)
                for item in root.findall(".//item"):
                    title = item.findtext("title", "").strip()
                    company_raw = item.findtext("source", "") or ""
                    link = item.findtext("link", "").strip()
                    desc = item.findtext("description", "").strip()
                    pub_date = item.findtext("pubDate", "")[:10] if item.findtext("pubDate") else ""

                    # extract company from title (Indeed format: "Job Title - Company")
                    company = ""
                    if " - " in title:
                        parts = title.rsplit(" - ", 1)
                        title = parts[0].strip()
                        company = parts[1].strip() if len(parts) > 1 else company_raw

                    location_display = loc.replace("+", " ").replace("%2C", ",")
                    jobs.append(normalize_job(
                        title=title,
                        company=company or "Unknown",
                        location=location_display,
                        description=desc,
                        url=link,
                        date_posted=pub_date,
                        source="Indeed",
                    ))
            except Exception as e:
                pass  # Indeed often blocks — silent fail

    print(f"  Found {len(jobs)} jobs from Indeed")
    return jobs


# ─────────────────────────────────────────────
# SOURCE 3 — REMOTIVE API (Remote jobs, free)
# ─────────────────────────────────────────────

def search_remotive():
    print("\n[3/6] Searching Remotive (remote jobs)...")
    jobs = []
    search_terms = ["machine-learning", "ai", "llm", "data-science"]

    for term in search_terms:
        try:
            resp = requests.get(
                f"https://remotive.com/api/remote-jobs?category={term}&limit=50",
                timeout=15
            )
            resp.raise_for_status()
            data = resp.json().get("jobs", [])
            cutoff = datetime.now(timezone.utc).replace(tzinfo=None)
            for j in data:
                pub_date_str = j.get("publication_date", "")[:10]
                try:
                    pub_date = datetime.strptime(pub_date_str, "%Y-%m-%d")
                    if (cutoff - pub_date).days > DAYS_POSTED:
                        continue
                except:
                    pass
                jobs.append(normalize_job(
                    title=j.get("title", ""),
                    company=j.get("company_name", ""),
                    location="Remote",
                    description=j.get("description", "")[:1000],
                    url=j.get("url", ""),
                    date_posted=pub_date_str,
                    source="Remotive",
                ))
        except Exception as e:
            print(f"  Remotive error: {e}")

    print(f"  Found {len(jobs)} jobs from Remotive")
    return jobs


# ─────────────────────────────────────────────
# SOURCE 4 — THE MUSE API (free, no key needed)
# ─────────────────────────────────────────────

def search_the_muse():
    print("\n[4/6] Searching The Muse...")
    jobs = []
    categories = ["Software Engineer", "Data Science", "QA", "IT & Systems"]

    for cat in categories:
        try:
            resp = requests.get(
                "https://www.themuse.com/api/public/jobs",
                params={
                    "category": cat,
                    "level": "Entry Level,Mid Level",
                    "page": 1,
                },
                timeout=15
            )
            resp.raise_for_status()
            data = resp.json().get("results", [])
            for j in data:
                title = j.get("name", "")
                # only keep AI/ML relevant roles
                title_lower = title.lower()
                if not any(kw in title_lower for kw in [
                    "machine learning", "ai ", "ml ", "data science",
                    "llm", "nlp", "deep learning", "artificial intelligence"
                ]):
                    continue
                company = j.get("company", {}).get("name", "")
                locations = j.get("locations", [])
                loc = locations[0].get("name", "Remote") if locations else "Remote"
                url = j.get("refs", {}).get("landing_page", "")
                pub_date = j.get("publication_date", "")[:10]
                desc = " ".join(
                    section.get("body", "") for section in j.get("contents", [])
                )[:1000]
                jobs.append(normalize_job(
                    title=title, company=company, location=loc,
                    description=desc, url=url, date_posted=pub_date, source="The Muse",
                ))
        except Exception as e:
            print(f"  The Muse error: {e}")

    print(f"  Found {len(jobs)} jobs from The Muse")
    return jobs


# ─────────────────────────────────────────────
# SOURCE 5 — YC WORK AT A STARTUP
# ─────────────────────────────────────────────

def search_yc_jobs():
    print("\n[5/6] Searching YC Work at a Startup...")
    jobs = []
    try:
        resp = requests.get(
            "https://www.workatastartup.com/jobs",
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            },
            params={
                "query": "machine learning AI engineer",
                "eng_type": "full-stack,backend",
                "remote": "true,onsite",
            },
            timeout=15
        )
        # YC doesn't have a public JSON API — generate search URLs instead
        # and add as curated links in the email
    except:
        pass

    # Instead — use their search page URLs as direct links
    yc_links = [
        {
            "title": "AI/ML Engineer Roles — YC Startups",
            "company": "Y Combinator Portfolio",
            "location": "Remote / USA",
            "description": "Current AI and ML engineering roles at YC-backed startups. Click to view all active listings posted this week.",
            "url": "https://www.workatastartup.com/jobs?query=machine+learning+AI&remote=true",
            "date_posted": datetime.now().strftime("%Y-%m-%d"),
            "source": "YC Work at a Startup",
            "salary_min": 0,
            "salary_max": 0,
        },
        {
            "title": "LLM / GenAI Engineer — YC Startups",
            "company": "Y Combinator Portfolio",
            "location": "Remote / USA",
            "description": "LLM and Generative AI engineering roles at early-stage YC companies. Strong equity upside. Applications reviewed directly by founders.",
            "url": "https://www.workatastartup.com/jobs?query=LLM+generative+AI&remote=true",
            "date_posted": datetime.now().strftime("%Y-%m-%d"),
            "source": "YC Work at a Startup",
            "salary_min": 0,
            "salary_max": 0,
        }
    ]
    jobs.extend(yc_links)
    print(f"  Found {len(jobs)} YC job links")
    return jobs


# ─────────────────────────────────────────────
# SOURCE 6 — WELLFOUND (AngelList)
# ─────────────────────────────────────────────

def search_wellfound():
    print("\n[6/6] Searching Wellfound (startup jobs)...")
    # Wellfound blocks API scraping — generate curated search URLs
    jobs = [
        {
            "title": "Machine Learning Engineer — Startups",
            "company": "Wellfound Startups",
            "location": "Remote / USA",
            "description": "Early-stage startup ML Engineer roles on Wellfound. Filtered for remote and US-based positions posted this week. Strong equity packages.",
            "url": "https://wellfound.com/jobs?role=machine-learning-engineer&remote=true&slug=machine-learning-engineer",
            "date_posted": datetime.now().strftime("%Y-%m-%d"),
            "source": "Wellfound",
            "salary_min": 0,
            "salary_max": 0,
        },
        {
            "title": "AI Engineer — Funded Startups",
            "company": "Wellfound Startups",
            "location": "Remote / USA",
            "description": "AI Engineer roles at seed through Series B startups. Click to browse all active listings on Wellfound filtered for your profile.",
            "url": "https://wellfound.com/jobs?role=artificial-intelligence-engineer&remote=true",
            "date_posted": datetime.now().strftime("%Y-%m-%d"),
            "source": "Wellfound",
            "salary_min": 0,
            "salary_max": 0,
        },
    ]
    print(f"  Found {len(jobs)} Wellfound job links")
    return jobs


# ─────────────────────────────────────────────
# SOURCE 7 — LINKEDIN (pre-filtered search URLs as job cards)
# ─────────────────────────────────────────────

def search_linkedin():
    print("\n[7/8] Generating LinkedIn job search cards...")

    # LinkedIn GeoIDs for target locations
    geo_ids = {
        "Remote (USA)":  ("103644278", "&f_WT=2"),
        "Boston MA":     ("100506914", ""),
        "San Francisco": ("102277331", ""),
        "New York":      ("102571732", ""),
        "Seattle":       ("103644278", ""),
    }

    jobs = []
    role_url_pairs = [
        ("AI Engineer",               "AI+Engineer"),
        ("ML Engineer",               "ML+Engineer"),
        ("LLM Engineer",              "LLM+Engineer"),
        ("Generative AI Engineer",    "Generative+AI+Engineer"),
        ("Applied AI Engineer",       "Applied+AI+Engineer"),
        ("Machine Learning Engineer", "Machine+Learning+Engineer"),
    ]

    for role_label, role_query in role_url_pairs:
        for loc_name, (geo_id, remote_flag) in geo_ids.items():
            url = (
                f"https://www.linkedin.com/jobs/search/"
                f"?keywords={role_query}"
                f"&geoId={geo_id}"
                f"&f_TPR=r604800"   # last 7 days
                f"&f_E=1%2C2%2C3"  # entry, associate, mid-senior
                f"{remote_flag}"
                f"&sortBy=DD"
            )
            jobs.append({
                "title": f"{role_label}",
                "company": f"LinkedIn — {loc_name}",
                "location": loc_name,
                "description": (
                    f"Pre-filtered LinkedIn search for {role_label} roles in {loc_name}. "
                    f"Filtered: posted last 7 days, entry to mid-level experience. "
                    f"Click Apply Now to open the search and browse all current listings."
                ),
                "url": url,
                "date_posted": datetime.now().strftime("%Y-%m-%d"),
                "source": "LinkedIn",
                "salary_min": 0,
                "salary_max": 0,
            })

    print(f"  Generated {len(jobs)} LinkedIn search cards")
    return jobs


# ─────────────────────────────────────────────
# SOURCE 8 — GITHUB JOB REPOS + EARLY CAREER BOARDS
# ─────────────────────────────────────────────

def search_github_and_early_career():
    print("\n[8/8] Adding GitHub repos + early career boards...")

    jobs = [
        # GitHub curated ML job repos
        {
            "title": "ML/AI Jobs — GitHub Awesome Lists",
            "company": "GitHub Community",
            "location": "Remote / USA",
            "description": (
                "Curated GitHub repositories listing ML and AI engineering roles. "
                "Updated frequently by the community. Includes early-career and "
                "new-grad friendly positions at AI startups and research labs."
            ),
            "url": "https://github.com/rShetty/awesome-distributed-systems",
            "date_posted": datetime.now().strftime("%Y-%m-%d"),
            "source": "GitHub",
            "salary_min": 0,
            "salary_max": 0,
        },
        {
            "title": "New Grad ML/AI Roles 2025-2026",
            "company": "GitHub — SimplifyJobs",
            "location": "Remote / USA",
            "description": (
                "The most comprehensive list of new grad and early career ML/AI "
                "software engineering jobs, maintained by SimplifyJobs on GitHub. "
                "Updated daily. Includes roles at FAANG, startups, and research labs. "
                "Filter by role type and location."
            ),
            "url": "https://github.com/SimplifyJobs/New-Grad-Positions",
            "date_posted": datetime.now().strftime("%Y-%m-%d"),
            "source": "GitHub",
            "salary_min": 0,
            "salary_max": 0,
        },
        {
            "title": "Summer 2026 Internships + Entry Level — ML/AI",
            "company": "GitHub — Pitt CSC & Simplify",
            "location": "Remote / USA",
            "description": (
                "Actively maintained GitHub repo tracking ML/AI internship and "
                "new-grad full-time positions for 2025-2026. "
                "Includes company, role, location, and direct application links. "
                "One of the most-watched job tracking repos on GitHub."
            ),
            "url": "https://github.com/pittcsc/Summer2025-Internships",
            "date_posted": datetime.now().strftime("%Y-%m-%d"),
            "source": "GitHub",
            "salary_min": 0,
            "salary_max": 0,
        },
        # Early career boards
        {
            "title": "AI/ML Engineer — Handshake Early Career",
            "company": "Handshake",
            "location": "Remote / USA / Boston",
            "description": (
                "Handshake is the leading early career job platform. "
                "Search for AI Engineer, ML Engineer, and LLM Engineer roles "
                "specifically posted for new grads and students graduating in 2026. "
                "Many roles are exclusive to Handshake and not on other job boards."
            ),
            "url": "https://app.joinhandshake.com/jobs?query=machine+learning+AI+engineer&workplace_type=remote%2Con_site&is_entry_level=true",
            "date_posted": datetime.now().strftime("%Y-%m-%d"),
            "source": "Handshake",
            "salary_min": 0,
            "salary_max": 0,
        },
        {
            "title": "ML Engineer — Levels.fyi Job Board",
            "company": "Levels.fyi",
            "location": "Remote / USA",
            "description": (
                "Levels.fyi job board with verified compensation data. "
                "Filter specifically for ML Engineer and AI Engineer roles with "
                "transparent salary ranges. Best for comparing offers and "
                "understanding market compensation before negotiating."
            ),
            "url": "https://www.levels.fyi/jobs?jobType=fulltime&query=machine+learning",
            "date_posted": datetime.now().strftime("%Y-%m-%d"),
            "source": "Levels.fyi",
            "salary_min": 0,
            "salary_max": 0,
        },
        {
            "title": "AI/ML Jobs — Jobright.ai",
            "company": "Jobright.ai",
            "location": "Remote / USA",
            "description": (
                "Jobright.ai aggregates AI/ML jobs from across the web and "
                "uses AI to match them to your profile. Strong coverage of "
                "roles not found on major job boards. Updated daily. "
                "Particularly good for finding roles at AI-native companies."
            ),
            "url": "https://jobright.ai/jobs/ai-and-machine-learning?experience=Entry+Level&location=United+States",
            "date_posted": datetime.now().strftime("%Y-%m-%d"),
            "source": "Jobright.ai",
            "salary_min": 0,
            "salary_max": 0,
        },
        {
            "title": "ML/AI Engineer — BuiltIn Boston",
            "company": "BuiltIn Boston",
            "location": "Boston, MA / Remote",
            "description": (
                "BuiltIn Boston lists tech and ML roles specifically at "
                "Boston-area startups and tech companies. Strong concentration "
                "of biotech AI, robotics, and software companies hiring in the "
                "Boston corridor. Great for staying local while joining high-growth teams."
            ),
            "url": "https://www.builtinboston.com/jobs/dev-engineer/machine-learning?experienceLevel=entry-level&remote=true",
            "date_posted": datetime.now().strftime("%Y-%m-%d"),
            "source": "BuiltIn Boston",
            "salary_min": 0,
            "salary_max": 0,
        },
    ]

    print(f"  Generated {len(jobs)} GitHub + early career board cards")
    return jobs


# ─────────────────────────────────────────────
# CLAUDE API — RESUME + COVER LETTER
# ─────────────────────────────────────────────

def generate_resume_and_cover_letter(job):
    title   = job.get("title", "N/A")
    company = job.get("company", "N/A")
    desc    = job.get("description", "")[:2500]

    prompt = f"""You are helping Piyush Kunjilwar apply for a job.

JOB TITLE: {title}
COMPANY: {company}
JOB DESCRIPTION:
{desc}

PIYUSH'S MASTER RESUME:
{MASTER_RESUME}

Generate TWO things:

1. TAILORED RESUME
Rewrite Piyush's resume for this specific role. Keep all facts 100% truthful.
Reorder and emphasize what matters most for this job.
Each bullet point must be on its own line starting with a dash.
Use clear section headers in ALL CAPS.
Keep same structure as the master resume.

2. COVER LETTER
Write a complete human-toned cover letter for this specific role.
- Sound like a real person wrote it, not AI
- Open with something specific about this company or role — not generic
- Connect Piyush's actual experience directly to what this job needs
- Include specific numbers and achievements from his resume
- Warm, confident, direct — not corporate or stiff
- 4-5 paragraphs with blank line between each
- Natural close — not desperate

PLAIN TEXT VERSION:
After the cover letter, write a plain text version of the resume with no special formatting — 
just clean text that can be pasted into any web form text field.

FORMAT — use EXACTLY these separators:
===RESUME===
[tailored resume]
===COVER LETTER===
[cover letter]
===PLAIN TEXT RESUME===
[plain text resume for form fields]"""

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": os.getenv("ANTHROPIC_API_KEY", ""),
                "anthropic-version": "2023-06-01"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 3500,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=90
        )
        resp.raise_for_status()
        full_text = resp.json()["content"][0]["text"]

        resume = cover_letter = plain_text = ""

        if "===RESUME===" in full_text:
            after_resume = full_text.split("===RESUME===")[1]
            if "===COVER LETTER===" in after_resume:
                resume = after_resume.split("===COVER LETTER===")[0].strip()
                after_cover = after_resume.split("===COVER LETTER===")[1]
                if "===PLAIN TEXT RESUME===" in after_cover:
                    cover_letter = after_cover.split("===PLAIN TEXT RESUME===")[0].strip()
                    plain_text = after_cover.split("===PLAIN TEXT RESUME===")[1].strip()
                else:
                    cover_letter = after_cover.strip()
                    plain_text = MASTER_RESUME
            else:
                resume = after_resume.strip()
                cover_letter = f"Dear {company} Team,\n\nI am excited to apply for the {title} role."
                plain_text = MASTER_RESUME
        else:
            resume = MASTER_RESUME
            cover_letter = f"Dear {company} Team,\n\nI am excited to apply for the {title} role."
            plain_text = MASTER_RESUME

        return resume, cover_letter, plain_text

    except Exception as e:
        print(f"  Claude API error: {e}")
        fallback_cover = f"""Dear {company} Team,

I am writing to apply for the {title} position. As an ML Engineer finishing my MS at Northeastern in May 2026, I bring hands-on production experience in distributed LLM training, agentic AI systems, and inference optimization.

At CareerGPT I built distributed training infrastructure using PyTorch FSDP across multi-node GPU clusters, reducing fine-tuning costs by 40%. I also engineered a Deep Research agentic workflow and optimized inference pipelines achieving 3.5x latency reduction through CUDA profiling and ONNX quantization.

I would love to discuss how my background aligns with what you are building at {company}.

Thank you,
Piyush Kunjilwar
(617) 516-9145"""
        return MASTER_RESUME, fallback_cover, MASTER_RESUME


# ─────────────────────────────────────────────
# FORMAT EMAIL
# ─────────────────────────────────────────────

def text_to_html(text):
    if not text:
        return ""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    lines = text.split("\n")
    html_lines = []
    for line in lines:
        s = line.strip()
        if not s:
            html_lines.append('<div style="height:8px;"></div>')
        elif s.isupper() and len(s) > 3 and len(s) < 60:
            html_lines.append(f'<div style="font-weight:bold;font-size:13px;margin-top:14px;margin-bottom:4px;color:#0a66c2;border-bottom:1px solid #ccc;padding-bottom:3px;">{s}</div>')
        elif s.startswith("- ") or s.startswith("* "):
            html_lines.append(f'<div style="padding-left:16px;margin:3px 0;font-size:13px;">&#8226; {s[2:].strip()}</div>')
        else:
            html_lines.append(f'<div style="margin:3px 0;font-size:13px;">{s}</div>')
    return "\n".join(html_lines)


def cover_letter_to_html(text):
    if not text:
        return ""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    parts = []
    for para in paragraphs:
        inner = "<br>".join(l.strip() for l in para.split("\n") if l.strip())
        parts.append(f'<p style="margin:0 0 14px 0;line-height:1.75;color:#222;font-size:14px;">{inner}</p>')
    return "\n".join(parts)


def plain_text_to_html(text):
    if not text:
        return ""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<pre style="font-family:monospace;font-size:12px;white-space:pre-wrap;line-height:1.6;color:#333;margin:0;">{text}</pre>'


def source_badge(source):
    colors = {
        "Adzuna":                "#0066cc",
        "Indeed":                "#003399",
        "Remotive":              "#00897b",
        "The Muse":              "#8e24aa",
        "YC Work at a Startup":  "#e65100",
        "Wellfound":             "#c62828",
        "LinkedIn":              "#0a66c2",
        "GitHub":                "#24292e",
        "Handshake":             "#e8175d",
        "Levels.fyi":            "#00b84c",
        "Jobright.ai":           "#7c4dff",
        "BuiltIn Boston":        "#ff6b35",
    }
    color = colors.get(source, "#555")
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:10px;font-size:11px;margin-left:8px;">{source}</span>'


def format_job_section(job, rank, resume, cover_letter, plain_text):
    title    = job.get("title", "N/A")
    company  = job.get("company", "N/A")
    location = job.get("location", "N/A")
    url      = job.get("url", "#")
    sal_max  = job.get("salary_max", 0) or 0
    salary   = f"Up to ${int(sal_max):,}" if sal_max > 0 else "See listing"
    created  = job.get("date_posted", "")[:10]
    score    = score_job(job)
    source   = job.get("source", "")
    full_text = (title + job.get("description", "")).lower()
    startup_tag = " 🚀 STARTUP" if is_startup_role(full_text) else ""

    return f"""
<div style="border:2px solid #0a66c2;border-radius:12px;margin-bottom:40px;overflow:hidden;font-family:Arial,sans-serif;">

  <div style="background:#0a66c2;color:white;padding:16px 20px;">
    <h2 style="margin:0;font-size:17px;">#{rank} {title}{startup_tag} {source_badge(source)}</h2>
    <p style="margin:6px 0 0;font-size:13px;opacity:0.9;">
      {company} &nbsp;|&nbsp; {location} &nbsp;|&nbsp; {salary} &nbsp;|&nbsp; Posted: {created} &nbsp;|&nbsp; Score: {score}/100
    </p>
  </div>

  <div style="padding:20px;">

    <a href="{url}" style="display:inline-block;background:#28a745;color:white;padding:10px 24px;
       border-radius:6px;text-decoration:none;font-weight:bold;font-size:14px;margin-bottom:24px;">
       Apply Now &rarr;
    </a>

    <!-- COVER LETTER -->
    <div style="margin-bottom:24px;">
      <div style="background:#fff8e1;border-left:4px solid #ffc107;padding:10px 14px;margin-bottom:12px;font-weight:bold;font-size:14px;">
        COVER LETTER &mdash; Copy and paste into application
      </div>
      <div style="background:#fff;border:1px solid #ddd;border-radius:6px;padding:20px;">
        {cover_letter_to_html(cover_letter)}
      </div>
    </div>

    <!-- TAILORED RESUME (formatted) -->
    <div style="margin-bottom:24px;">
      <div style="background:#e3f2fd;border-left:4px solid #0a66c2;padding:10px 14px;margin-bottom:12px;font-weight:bold;font-size:14px;">
        TAILORED RESUME &mdash; For PDF/Word upload reference
      </div>
      <div style="background:#fafafa;border:1px solid #ddd;border-radius:6px;padding:20px;">
        {text_to_html(resume)}
      </div>
    </div>

    <!-- PLAIN TEXT RESUME (for form fields) -->
    <div>
      <div style="background:#f3e5f5;border-left:4px solid #7b1fa2;padding:10px 14px;margin-bottom:12px;font-weight:bold;font-size:14px;">
        PLAIN TEXT RESUME &mdash; Copy and paste into form text fields
      </div>
      <div style="background:#fafafa;border:1px solid #ddd;border-radius:6px;padding:16px;overflow-x:auto;">
        {plain_text_to_html(plain_text)}
      </div>
    </div>

  </div>
</div>
"""


def format_email_html(job_sections, stats):
    today = datetime.now().strftime("%B %d, %Y")
    all_sections = "".join(job_sections)

    source_breakdown = " &nbsp;|&nbsp; ".join(
        f"{src}: {count}" for src, count in stats["sources"].items()
    )

    linkedin_links = "".join([
        f'<li><a href="https://www.linkedin.com/jobs/search/?keywords={quote(role)}&f_TPR=r604800&f_E=1%2C2%2C3&f_WT=2&sortBy=DD">{role} — Remote</a></li>'
        for role in TARGET_ROLES[:6]
    ])

    return f"""<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;max-width:820px;margin:auto;padding:20px;background:#f5f5f5;">

  <div style="background:#0a66c2;color:white;padding:24px;border-radius:10px;margin-bottom:20px;">
    <h1 style="margin:0;font-size:22px;">AI/ML Job Digest + Application Kits</h1>
    <p style="margin:6px 0 0;opacity:0.9;">{today} &mdash; Piyush Kunjilwar</p>
    <p style="margin:4px 0 0;font-size:13px;opacity:0.8;">
      {stats['total']} total jobs found &nbsp;|&nbsp; {stats['filtered']} senior roles removed &nbsp;|&nbsp; {len(job_sections)} full kits generated
    </p>
    <p style="margin:4px 0 0;font-size:12px;opacity:0.7;">Sources: {source_breakdown}</p>
  </div>

  <div style="background:#d4edda;border:1px solid #c3e6cb;padding:16px 20px;border-radius:8px;margin-bottom:20px;color:#155724;font-size:14px;">
    <strong>How to apply in 3 minutes per job:</strong><br><br>
    1. Click Apply Now<br>
    2. Upload your existing PDF resume to the file upload field<br>
    3. Copy the Cover Letter into the cover letter field<br>
    4. Copy the Plain Text Resume into any work history / resume text fields<br>
    5. Submit
  </div>

  {all_sections}

  <div style="background:#fff;border:1px solid #ddd;border-radius:8px;padding:20px;margin-top:20px;">
    <h3 style="margin:0 0 12px;color:#0a66c2;">More Jobs — LinkedIn Quick Links</h3>
    <ul style="margin:0;padding-left:20px;line-height:2;">
      {linkedin_links}
    </ul>
    <p style="margin:12px 0 0;font-size:13px;">
      <a href="https://www.workatastartup.com/jobs?query=machine+learning+AI&remote=true">YC Work at a Startup &rarr;</a>
      &nbsp;&nbsp;
      <a href="https://wellfound.com/jobs?role=machine-learning-engineer&remote=true">Wellfound ML Jobs &rarr;</a>
      &nbsp;&nbsp;
      <a href="https://remotive.com/remote-jobs/software-dev/machine-learning">Remotive Remote ML &rarr;</a>
    </p>
  </div>

  <p style="color:#999;font-size:12px;text-align:center;margin-top:20px;">
    Auto-generated every morning at 8am EST &mdash; Job Search Agent for Piyush Kunjilwar
  </p>

</body>
</html>"""


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
    msg["Subject"] = f"{job_count} AI/ML Jobs — Cover Letters + Resumes Ready — {today}"
    msg["From"]    = sender
    msg["To"]      = recipient
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
    print("=" * 60)
    print("Job Search Agent — Multi-Source Edition")
    print("=" * 60)

    # collect from all sources
    all_jobs = []
    source_counts = {}

    sources = [
        ("Adzuna",              search_adzuna),
        ("Indeed",              search_indeed),
        ("Remotive",            search_remotive),
        ("The Muse",            search_the_muse),
        ("YC Work at a Startup",search_yc_jobs),
        ("Wellfound",           search_wellfound),
        ("LinkedIn",            search_linkedin),
        ("GitHub + Early Career", search_github_and_early_career),
    ]

    for source_name, source_fn in sources:
        try:
            jobs = source_fn()
            all_jobs.extend(jobs)
            source_counts[source_name] = len(jobs)
        except Exception as e:
            print(f"  {source_name} failed: {e}")
            source_counts[source_name] = 0

    print(f"\nTotal jobs collected: {len(all_jobs)}")

    # deduplicate
    unique_jobs = deduplicate(all_jobs)
    print(f"After deduplication: {len(unique_jobs)}")

    # filter by experience level
    filtered_jobs = [j for j in unique_jobs if should_include(j)]
    removed_count = len(unique_jobs) - len(filtered_jobs)
    print(f"After filtering senior roles: {len(filtered_jobs)} ({removed_count} removed)")

    # score and sort
    scored_jobs = sorted(filtered_jobs, key=score_job, reverse=True)
    top_jobs = scored_jobs[:TOP_JOBS_TO_PROCESS]
    print(f"Generating application kits for top {len(top_jobs)} jobs...\n")

    stats = {
        "total": len(unique_jobs),
        "filtered": removed_count,
        "sources": source_counts,
    }

    # generate resume + cover letter + plain text for each top job
    job_sections = []
    for i, job in enumerate(top_jobs):
        title   = job.get("title", "N/A")
        company = job.get("company", "N/A")
        source  = job.get("source", "")
        print(f"  [{i+1}/{len(top_jobs)}] {title} at {company} ({source})")
        resume, cover_letter, plain_text = generate_resume_and_cover_letter(job)
        section = format_job_section(job, i+1, resume, cover_letter, plain_text)
        job_sections.append(section)

    html = format_email_html(job_sections, stats)
    send_email(html, len(top_jobs))

    print(f"\nDone! {len(top_jobs)} application kits sent.")
    print("\nTop 5 jobs by score:")
    for i, job in enumerate(top_jobs[:5]):
        print(f"  #{i+1} [{score_job(job)}/100] {job.get('title')} at {job.get('company')} ({job.get('source')})")


if __name__ == "__main__":
    run()
