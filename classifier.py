"""Transparent rule-based demo classifier. Replace/augment with trained ML after dataset validation."""
import re

RULES = [
    ('Public Safety', 'High', ['fire', 'accident', 'electrocution', 'live wire', 'collapse', 'urgent danger', 'emergency']),
    ('Water Supply', 'High', ['no water', 'water supply', 'drinking water', 'tap water', 'water leakage', 'pipe burst', 'contaminated water']),
    ('Drainage', 'High', ['sewage', 'drainage', 'blocked drain', 'drain overflow', 'sewer overflow', 'manhole']),
    ('Electricity', 'High', ['street light', 'streetlight', 'power cut', 'electricity', 'transformer', 'exposed wire']),
    ('Sanitation', 'Medium', ['garbage', 'waste collection', 'dustbin', 'dumping', 'dirty street', 'cleaning', 'mosquito']),
    ('Roads and Transport', 'Medium', ['road', 'pothole', 'footpath', 'traffic signal', 'damaged bridge', 'road work']),
    ('Government Services', 'Normal', ['certificate', 'pension', 'ration card', 'government service', 'permit']),
]


def classify_complaint(text):
    cleaned = re.sub(r'\s+', ' ', (text or '').lower()).strip()
    for category, priority, keywords in RULES:
        if any(keyword in cleaned for keyword in keywords):
            return category, priority
    return 'General Complaint', 'Normal'


def suggested_worker(category):
    return {
        'Water Supply': 'Water Supply Team',
        'Drainage': 'Drainage Team',
        'Electricity': 'Electrical Team',
        'Sanitation': 'Sanitation Team',
        'Roads and Transport': 'Road Maintenance Team',
        'Public Safety': 'Public Safety Team',
        'Government Services': 'Citizen Services Team',
    }.get(category, 'General Field Team')
