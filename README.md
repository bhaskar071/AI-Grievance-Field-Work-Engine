# Digital Amaravati — DI-04 AI Grievance and Field-Work Engine

A local demonstration prototype aligned to the APCRDA Digital Amaravati Internship notification's DI-04 problem statement. It demonstrates text/photo/audio complaint intake, rule-based classification and priority suggestion, location coordinates, field-worker assignment, SLA deadlines, activity history, photo-backed resolution verification, and a public aggregate scorecard.

> This is an independent student demo, not an official APCRDA service. The classifier is rule-based, audio is stored but not automatically transcribed, and the public scorecard is not an official audited report.

## Features

- Citizen registration and login with password hashing.
- Role-separated citizen, admin and field-worker workspaces.
- Complaint text, optional photo and audio attachments, optional voice transcript, and optional GPS coordinates.
- Rule-based category and priority classification with suggested team and SLA deadline (High: 8h, Medium: 24h, Normal: 72h).
- Admin queue, filters, worker assignment, status management, overdue indicators and resolution verification.
- Field worker task list; a resolution photo is required before requesting verification.
- Activity history for workflow actions.
- Public aggregate scorecard without citizen names or complaint text.
- SQLite database, upload type allowlist, random upload filenames, request size limit, session-bound CSRF token checks, role checks, SQL parameters and password hashes.
- Health endpoint: `/health`.

## Windows / VS Code setup

1. Extract this ZIP into a new folder, for example `C:\Users\YOUR_NAME\Desktop\DI04_Final_Project`. Do not paste these files over your old project until you have a backup.
2. Open the extracted folder in VS Code.
3. Open Terminal → New Terminal.
4. Create a virtual environment:
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
   If PowerShell blocks activation, use Command Prompt terminal and run `.venv\Scripts\activate.bat`.
5. Install packages:
   ```powershell
   py -m pip install -r requirements.txt
   ```
6. Create the admin and worker accounts:
   ```powershell
   py setup_demo_accounts.py
   ```
   Choose unique demo passwords (at least 12 characters). The script prints account emails, not passwords.
7. Start the app:
   ```powershell
   py app.py
   ```
8. Open `http://127.0.0.1:5000/` in your browser. Keep the terminal open while testing.

## Demo flow

1. Register a citizen account and submit a road/water/drainage complaint. Try adding a photo and coordinates.
2. Log out. Log in as the admin account created by the setup script.
3. Assign the complaint to the demo worker account. Keep note of the complaint ID.
4. Log out. Log in as the worker and open the assigned complaint. Set status to `In Progress`; then upload a resolution photo and choose `Ready for verification`.
5. Log out and sign in as admin. Open the admin console, view evidence and approve or return it for rework.
6. Open `/scorecard` in a separate browser tab to demonstrate aggregate public metrics.

## Database and files

- SQLite data is created in `grievances.db`.
- Uploads are stored in `static/uploads/` under random filenames.
- Back up the database and uploads together if you need to preserve demo records.
- Do not delete `grievances.db` after entering test data.

## Important limitations and production work

- The classifier is an explainable keyword-rule baseline, not a trained ML model. Evaluate it against a labelled dataset before claiming model accuracy.
- Audio files are stored; automatic speech-to-text is not implemented. The citizen can provide a transcript in the form.
- Coordinates are optional and routing uses category/team suggestions; production GIS should validate location and crew jurisdiction.
- SLA hours are illustrative demo defaults, not APCRDA-approved policy. Confirm real SLAs with the mentor/authority.
- Public scorecard metrics are calculated from local demo records and should not be represented as official figures.
- This app is not production-hardened: deploy only behind HTTPS and a production WSGI server, set a strong `DI04_SECRET_KEY`, use secure cookie settings, scan uploaded media, add rate limiting/backups/monitoring, and obtain approval for real citizen data. Do not expose Flask's debug server to the internet.
- If using this as a submission, explain which parts are implemented, which are demo assumptions, and what would be integrated with APCRDA systems in a staging environment.
