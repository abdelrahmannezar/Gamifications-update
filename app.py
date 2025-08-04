from flask import Flask, render_template, request, redirect, url_for
import os
import pandas as pd
from datetime import datetime
import requests
from werkzeug.utils import secure_filename

# Create Flask app
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# === Configuration ===
CLIENT_ID = "364b8bf7-0be9-432e-952c-113ec31048f7"
CLIENT_SECRET = "8NJTT-uRXICuZpPOr52IeUqxQE-eh7SMstEGu-SQesg"
GENESYS_CLOUD_REGION = "mec1.pure.cloud"
user_id_cache = {}

def get_access_token():
    auth_url = f"https://login.{GENESYS_CLOUD_REGION}/oauth/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    try:
        response = requests.post(auth_url, headers=headers, data=data)
        response.raise_for_status()
        return response.json()["access_token"]
    except requests.exceptions.RequestException as e:
        print(f"❌ Error getting token: {e}")
        return None

def get_user_id_by_email(email, token):
    if email in user_id_cache:
        return user_id_cache[email]
    
    search_url = f"https://api.{GENESYS_CLOUD_REGION}/api/v2/users/search"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    query = {
        "query": [
            {
                "fields": ["email"],
                "value": email,
                "type": "EXACT"
            }
        ]
    }
    try:
        response = requests.post(search_url, headers=headers, json=query)
        response.raise_for_status()
        results = response.json().get('results')
        if results:
            user_id = results[0]['id']
            user_id_cache[email] = user_id
            return user_id
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ Error finding user '{email}': {e}")
        return None

def post_metric_data(token, metric_id, metric_data_list):
    upload_url = f"https://api.{GENESYS_CLOUD_REGION}/api/v2/employeeperformance/externalmetrics/data"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"items": metric_data_list}
    
    try:
        response = requests.post(upload_url, headers=headers, json=payload)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Upload failed: {e.response.text}")
        return False

# === Routes ===

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    metric_id = request.form.get('metric_id')
    excel_file = request.files.get('excel_file')

    if not excel_file or not metric_id:
        return "❌ Missing Metric ID or file", 400

    filename = secure_filename(excel_file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    excel_file.save(file_path)

    access_token = get_access_token()
    if not access_token:
        return "❌ Could not authenticate", 500

    df = pd.read_excel(file_path)
    metric_data_list = []

    for _, row in df.iterrows():
        email = row['AgentEmail']
        score = row['TestScore']
        date_str = row['Date'].strftime('%Y-%m-%d')
        user_id = get_user_id_by_email(email, access_token)

        if user_id:
            metric_data_list.append({
                "metricId": metric_id,
                "userId": user_id,
                "dateOccurred": datetime.strptime(date_str, '%Y-%m-%d').isoformat() + "Z",
                "value": float(score)
            })

    if metric_data_list:
        post_metric_data(access_token, metric_id, metric_data_list)

    return render_template('success.html')

if __name__ == '__main__':
    app.run(debug=True)
