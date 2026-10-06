# Job Application Tracker

A local web app for keeping job applications, contacts, follow-ups, and interview notes in one place. Paste a job posting link to fill in available job details, then edit them and track your progress.

Built with Python, Flask, SQLite, and plain HTML/CSS/JavaScript. No account, API key, or external database service is needed.

## Features

- Analyze a posting link for its title, company, location, description, work mode, employment type, salary, and dates when available.
- Track Wishlist, Applied, Screening, Interviewing, Offer, Accepted, Rejected, and Withdrawn statuses.
- Record contacts, referrals, resume versions, cover-letter usage, ratings, tags, notes, and next actions.
- Keep a timeline of interviews, emails, notes, and automatic status changes.
- Search by title, company, location, or tags; filter by status; sort by dates, company, or rating.
- Export the current filtered list to PDF.
- Store application data in a local SQLite file that is created on first run.

## Requirements

- Python 3.9 through 3.12. Python 3.11 or 3.12 is recommended for a new installation. The pinned dependencies have not been verified with Python 3.13 or later.
- A web browser.
- Internet access to install dependencies and analyze online job postings. Viewing and editing saved applications works offline, although remote company images may not load.

## Get the application

Clone the repository:

```bash
git clone https://github.com/difeigu/job_app_track.git
cd job_app_track
```

Alternatively, download the repository using **Code > Download ZIP**, or download the packaged source ZIP from **Releases** if available. Extract the ZIP and open a terminal in the folder containing `app.py` and `requirements.txt`. The package contains source code; Python and the dependencies must be installed separately.

## Install and run on Windows

In PowerShell or Command Prompt, run:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

If you installed Python 3.12, replace `py -3.11` with `py -3.12`. If the `py` launcher is unavailable, use `python -m venv .venv` with a supported Python installation instead. These commands do not require activating the environment or changing PowerShell's execution policy.

Open **http://127.0.0.1:5000** in your browser. Keep the terminal open while using the app. Press **Ctrl+C** in the terminal to stop it.

After setup, double-click `run.bat` or run it from the project folder to start the app again. Open the same browser address.

## Install and run on macOS or Linux

Use a supported Python version:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

Open **http://127.0.0.1:5000**. Press **Ctrl+C** in the terminal to stop the app. Start it again with `.venv/bin/python app.py`.

## Use the tracker

### Add an application

1. Click **+ Add Application**.
2. Paste the job posting URL and click **Fetch & Add**.
3. Review the extracted details in the application window. Fill in missing fields or correct anything that was inferred incorrectly.
4. Choose a status and adjust the applied date, then click **Save**. New applications start as **Applied** with today's UTC date; change them to **Wishlist** and clear the applied date when saving a role for later.

The app saves the link even when a site cannot be analyzed, so you can complete the details manually. Adding a link records it in the tracker; submit your actual job application on the employer's site.

### Update progress and details

Click an application card to edit its job information, compensation, status, dates, contacts, and notes. You can also change its status directly on the card. Status changes automatically add a timeline entry.

Use **Next Action** and **Next Action Date** to record a planned follow-up. These are saved fields; the app does not send reminders or emails. **Resume version** records a label or filename; resumes and cover letters are not uploaded.

Click **Open Application** to revisit the original posting. **Re-analyze Link** fetches it again and can replace previously saved job fields when fresh values are found, so review the results afterward.

### Add timeline entries

Open a card and scroll to **Timeline**. Choose an event type, enter a date and description, then click **Add**. Timeline entries save immediately. Use the delete control beside an entry to remove it. **Delete** at the bottom of the application window removes the application and its timeline permanently.

### Find applications and export a PDF

Use the search box, status selector, or status counters to narrow the list. Choose an order from the sort selector. Click **Export PDF** to download a table of the currently filtered applications in the selected order.

The PDF includes company, title, status, location, work mode, salary, applied date, and deadline. It is a summary, not a full database backup. Some characters outside the PDF's built-in font encoding appear as `?`.

## Database, privacy, and backups

The first launch creates `data/jobs.db` beside the application source. Your entries remain there between runs. The published repository and source package contain no existing database, saved applications, or scraped-page debug captures.

The server listens on `127.0.0.1` and runs with Flask debugging disabled. It is intended for personal use on your own computer and has no login system. Keep it bound to that local address.

When you analyze a link, the app makes a request to the posting website. Your browser may also request externally hosted company images. Other application data is stored locally.

To back up your data:

1. Stop the app with **Ctrl+C**.
2. Copy `data/jobs.db` to a private backup location.
3. To restore or move to another computer, stop the destination app and place the backup at its `data/jobs.db` path. Replacing an existing database replaces its saved applications, so back it up first.

The `.gitignore` excludes the entire `data/` folder, SQLite files and their sidecars, virtual environments, credentials, local debug captures, and generated packages. Keep personal backups outside the repository and never force-add ignored data files.

## How link analysis works

The scraper first looks for embedded `schema.org/JobPosting` JSON-LD data. It also supports some Meta Careers page data and falls back to page metadata and URL/text heuristics. It makes a regular HTTP request and does not run a browser or sign in to job boards.

Some postings require login, rely on JavaScript, have expired, or block automated requests. Extraction may therefore be incomplete or incorrect. Review the details and enter missing information manually.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| Python or `py` is not found | Install a supported Python version and reopen the terminal. On Windows, you can use the full path to `python.exe` instead of `py`. |
| A module such as `flask` or `fpdf` is missing | Run the dependency-install command with the same `.venv` Python used to start the app. The PDF dependency is `fpdf2`. |
| Dependency installation fails on a newer Python version | Recreate `.venv` using Python 3.11 or 3.12, then install `requirements.txt` again. |
| Port 5000 is already in use | Stop the other process using that port or an earlier instance of this app, then start again. |
| The browser cannot connect | Keep the server terminal open and use `http://127.0.0.1:5000` with HTTP. Read any error shown in the terminal. |
| Link analysis fails or has missing details | Save the link, enter details manually, and retry **Re-analyze Link** later if needed. |
| No applications appear after moving the app | The new folder starts with a new database. Restore your private backup to `data/jobs.db` with the app stopped. |

## Build a clean source package

On Windows, run from the project folder:

```powershell
powershell -NoProfile -File .\scripts\package.ps1
```

This creates `dist/job_app_track-1.0.0.zip`. The script uses an explicit list of public source files and does not recursively copy the project folder, so the database, virtual environment, credentials, and local captures are excluded. If PowerShell blocks local scripts, inspect the script and follow your organization's policy for running it.

## Project layout

```text
app.py                  Flask routes and PDF export
db.py                   SQLite schema and connection helpers
scraper.py              Job posting extraction
requirements.txt        Python dependencies
run.bat                 Windows launcher after setup
templates/index.html    Application page
static/css/style.css    Styles
static/js/app.js         Browser interactions
scripts/package.ps1     Source ZIP builder
data/jobs.db            Your local data (created at runtime; ignored)
```
