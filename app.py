from datetime import datetime, timezone

from flask import Flask, Response, jsonify, render_template, request
from fpdf import FPDF

from db import get_db, init_db
from scraper import scrape_job

app = Flask(__name__)


@app.errorhandler(Exception)
def handle_unexpected_error(exc):
    from werkzeug.exceptions import HTTPException
    if isinstance(exc, HTTPException):
        return jsonify({"error": exc.description}), exc.code
    app.logger.exception("Unhandled error")
    return jsonify({"error": f"{exc.__class__.__name__}: {exc}"}), 500


APPLICATION_FIELDS = [
    "url", "title", "company", "company_logo", "location", "work_mode",
    "employment_type", "status", "source", "salary_min", "salary_max",
    "salary_currency", "salary_period", "description", "date_posted",
    "deadline", "contact_name", "contact_email", "contact_phone",
    "referral", "resume_version", "cover_letter_used", "rating", "tags",
    "applied_date", "next_action", "next_action_date", "notes",
]

STATUSES = [
    "Wishlist", "Applied", "Screening", "Interviewing",
    "Offer", "Accepted", "Rejected", "Withdrawn",
]


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def row_to_dict(row):
    return {k: row[k] for k in row.keys()}


SORT_MAP = {
    "created_desc": "created_at DESC",
    "created_asc": "created_at ASC",
    "applied_desc": "applied_date DESC",
    "deadline_asc": "deadline ASC",
    "company_asc": "company ASC",
    "rating_desc": "rating DESC",
}


def build_applications_query(status, q, sort):
    order_by = SORT_MAP.get(sort, "created_at DESC")
    query = "SELECT * FROM applications"
    clauses, params = [], []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if q:
        clauses.append("(title LIKE ? OR company LIKE ? OR location LIKE ? OR tags LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like, like])
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += f" ORDER BY {order_by}"
    return query, params


def fmt_money(row):
    lo, hi = row["salary_min"], row["salary_max"]
    if not lo and not hi:
        return ""
    cur = row["salary_currency"] or ""
    period = f"/{row['salary_period'].lower()}" if row["salary_period"] else ""
    if lo and hi and lo != hi:
        return f"{cur} {int(lo):,}-{int(hi):,}{period}".strip()
    val = lo or hi
    return f"{cur} {int(val):,}{period}".strip()


def pdf_safe(text):
    if text is None:
        return ""
    return str(text).encode("latin-1", "replace").decode("latin-1")


@app.route("/")
def index():
    return render_template("index.html", statuses=STATUSES)


@app.route("/api/statuses")
def api_statuses():
    return jsonify(STATUSES)


@app.route("/api/scrape", methods=["POST"])
def api_scrape():
    body = request.get_json(force=True, silent=True) or {}
    url = (body.get("url") or "").strip()
    if not url:
        return jsonify({"error": "url is required"}), 400
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    data = scrape_job(url)
    return jsonify(data)


@app.route("/api/applications", methods=["GET"])
def list_applications():
    status = request.args.get("status")
    q = request.args.get("q")
    sort = request.args.get("sort", "created_desc")

    conn = get_db()
    try:
        query, params = build_applications_query(status, q, sort)
        rows = conn.execute(query, params).fetchall()

        counts = conn.execute(
            "SELECT status, COUNT(*) as n FROM applications GROUP BY status"
        ).fetchall()
        counts_dict = {r["status"]: r["n"] for r in counts}

        return jsonify({
            "applications": [row_to_dict(r) for r in rows],
            "counts": counts_dict,
            "total": len(rows),
        })
    finally:
        conn.close()


@app.route("/api/export/pdf", methods=["GET"])
def export_pdf():
    status = request.args.get("status")
    q = request.args.get("q")
    sort = request.args.get("sort", "created_desc")

    conn = get_db()
    try:
        query, params = build_applications_query(status, q, sort)
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Job Application Tracker", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 9)
    subtitle = f"Exported {datetime.now().strftime('%Y-%m-%d %H:%M')} — {len(rows)} application(s)"
    if status:
        subtitle += f" — status: {status}"
    if q:
        subtitle += f" — search: \"{q}\""
    pdf.cell(0, 6, pdf_safe(subtitle), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    headers = ["Company", "Title", "Status", "Location", "Work Mode", "Salary", "Applied", "Deadline"]
    col_widths = [40, 60, 26, 40, 24, 38, 22, 22]

    pdf.set_font("Helvetica", "B", 9)
    with pdf.table(col_widths=col_widths, text_align="LEFT") as table:
        header_row = table.row()
        for h in headers:
            header_row.cell(h)

        pdf.set_font("Helvetica", "", 8)
        for r in rows:
            row = table.row()
            row.cell(pdf_safe(r["company"]))
            row.cell(pdf_safe(r["title"]))
            row.cell(pdf_safe(r["status"]))
            row.cell(pdf_safe(r["location"]))
            row.cell(pdf_safe(r["work_mode"]))
            row.cell(pdf_safe(fmt_money(r)))
            row.cell(pdf_safe(r["applied_date"]))
            row.cell(pdf_safe(r["deadline"]))

    filename = f"job_applications_{datetime.now().strftime('%Y%m%d')}.pdf"
    return Response(
        bytes(pdf.output()),
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/api/applications", methods=["POST"])
def create_application():
    body = request.get_json(force=True, silent=True) or {}
    url = (body.get("url") or "").strip()
    if not url:
        return jsonify({"error": "url is required"}), 400
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    scrape_status, scrape_message = None, None
    if not body.get("title") and not body.get("company"):
        scraped = scrape_job(url)
        scrape_status = scraped.pop("scrape_status", None)
        scrape_message = scraped.pop("scrape_message", None)
        for key, value in scraped.items():
            if key in APPLICATION_FIELDS and not body.get(key):
                body[key] = value

    body["url"] = url
    timestamp = now_iso()
    body.setdefault("status", "Applied")
    body.setdefault("applied_date", timestamp[:10])

    fields = {k: body.get(k) for k in APPLICATION_FIELDS if k in body}

    conn = get_db()
    try:
        columns = list(fields.keys()) + ["scrape_status", "scrape_message", "created_at", "updated_at"]
        values = list(fields.values()) + [scrape_status, scrape_message, timestamp, timestamp]
        placeholders = ", ".join(["?"] * len(columns))
        cur = conn.execute(
            f"INSERT INTO applications ({', '.join(columns)}) VALUES ({placeholders})",
            values,
        )
        conn.commit()
        new_id = cur.lastrowid

        conn.execute(
            "INSERT INTO events (application_id, event_type, event_date, description, created_at) "
            "VALUES (?, 'Status Change', ?, ?, ?)",
            (new_id, timestamp[:10], f"Added to tracker as {fields.get('status', 'Wishlist')}", timestamp),
        )
        conn.commit()

        row = conn.execute("SELECT * FROM applications WHERE id = ?", (new_id,)).fetchone()
        return jsonify(row_to_dict(row)), 201
    finally:
        conn.close()


@app.route("/api/applications/<int:app_id>", methods=["GET"])
def get_application(app_id):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        events = conn.execute(
            "SELECT * FROM events WHERE application_id = ? ORDER BY event_date DESC, id DESC",
            (app_id,),
        ).fetchall()
        data = row_to_dict(row)
        data["events"] = [row_to_dict(e) for e in events]
        return jsonify(data)
    finally:
        conn.close()


@app.route("/api/applications/<int:app_id>", methods=["PATCH", "PUT"])
def update_application(app_id):
    body = request.get_json(force=True, silent=True) or {}
    conn = get_db()
    try:
        existing = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
        if not existing:
            return jsonify({"error": "not found"}), 404

        fields = {k: v for k, v in body.items() if k in APPLICATION_FIELDS}
        if not fields:
            return jsonify({"error": "no valid fields to update"}), 400

        if "status" in fields and fields["status"] != existing["status"]:
            conn.execute(
                "INSERT INTO events (application_id, event_type, event_date, description, created_at) "
                "VALUES (?, 'Status Change', ?, ?, ?)",
                (app_id, now_iso()[:10], f"Status changed from {existing['status']} to {fields['status']}", now_iso()),
            )

        fields["updated_at"] = now_iso()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(
            f"UPDATE applications SET {set_clause} WHERE id = ?",
            list(fields.values()) + [app_id],
        )
        conn.commit()

        row = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
        return jsonify(row_to_dict(row))
    finally:
        conn.close()


@app.route("/api/applications/<int:app_id>", methods=["DELETE"])
def delete_application(app_id):
    conn = get_db()
    try:
        conn.execute("DELETE FROM applications WHERE id = ?", (app_id,))
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()


@app.route("/api/applications/<int:app_id>/rescrape", methods=["POST"])
def rescrape_application(app_id):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        scraped = scrape_job(row["url"])
        scrape_status = scraped.pop("scrape_status", None)
        scrape_message = scraped.pop("scrape_message", None)
        fields = {k: v for k, v in scraped.items() if k in APPLICATION_FIELDS and v}
        fields["scrape_status"] = scrape_status
        fields["scrape_message"] = scrape_message
        fields["updated_at"] = now_iso()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(
            f"UPDATE applications SET {set_clause} WHERE id = ?",
            list(fields.values()) + [app_id],
        )
        conn.commit()
        row = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
        return jsonify(row_to_dict(row))
    finally:
        conn.close()


@app.route("/api/applications/<int:app_id>/events", methods=["POST"])
def add_event(app_id):
    body = request.get_json(force=True, silent=True) or {}
    event_type = body.get("event_type", "Note")
    event_date = body.get("event_date") or now_iso()[:10]
    description = body.get("description", "")

    conn = get_db()
    try:
        existing = conn.execute("SELECT id FROM applications WHERE id = ?", (app_id,)).fetchone()
        if not existing:
            return jsonify({"error": "not found"}), 404
        cur = conn.execute(
            "INSERT INTO events (application_id, event_type, event_date, description, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (app_id, event_type, event_date, description, now_iso()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM events WHERE id = ?", (cur.lastrowid,)).fetchone()
        return jsonify(row_to_dict(row)), 201
    finally:
        conn.close()


@app.route("/api/events/<int:event_id>", methods=["DELETE"])
def delete_event(event_id):
    conn = get_db()
    try:
        conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000)
