import csv
import json
import hashlib
import os

csv_path = "private/sam_entities.csv"
output_path = "Frontend/orbitavanya/src/data/companies.json"

companies = []

def get_stable_hash(name, salt):
    h = hashlib.md5((name + salt).encode('utf-8')).hexdigest()
    return int(h, 16)

def generate_revenue(name):
    h = get_stable_hash(name, "revenue")
    val = h % 499 + 1 # 1M to 500M
    return f"${val}M"

def generate_size(name, is_small):
    h = get_stable_hash(name, "size")
    if is_small == 'Y':
        sizes = ['10-50', '50-100', '100-200', '200-500']
        return sizes[h % len(sizes)]
    else:
        sizes = ['500-1000', '1000-5000', '5000-10000', '10000+']
        return sizes[h % len(sizes)]

def generate_score(name):
    h = get_stable_hash(name, "score")
    return 75 + (h % 25) # 75 to 99

if not os.path.exists(csv_path):
    print(f"Error: {csv_path} not found")
    exit(1)

with open(csv_path, mode='r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for idx, row in enumerate(reader):
        name = row.get('Legal_Business_Name', '').strip()
        if not name:
            name = row.get('DBA_Name', '').strip()
        if not name:
            continue
        
        # Determine industry
        industry = row.get('Primary_NAICS_Description', '').strip()
        if not industry:
            industry = row.get('Entity_Structure', '').strip()
        if not industry:
            industry = 'Services'
        # Clean up industry names that are too long
        if len(industry) > 50:
            industry = industry[:47] + "..."
            
        # Determine location
        city = row.get('Phys_City', '').strip().title()
        state = row.get('Phys_State_Province', '').strip().upper()
        country = row.get('Phys_Country', '').strip().upper()
        
        if city and state:
            location = f"{city}, {state}"
        elif city:
            location = f"{city}, {country}"
        else:
            location = country if country else "Unknown"
            
        status = row.get('Registration_Status', 'Active').strip().title()
        
        contact = row.get('Gov_Contact_Name', '').strip()
        if not contact:
            contact = row.get('EBiz_Contact_Name', '').strip()
        if not contact:
            contact = "N/A"
            
        email = row.get('Gov_Contact_Email', '').strip()
        if not email:
            email = row.get('EBiz_Contact_Email', '').strip()
        if not email:
            # Generate email
            clean_name = "".join(c for c in name if c.isalnum()).lower()
            email = f"info@{clean_name[:15]}.com"
            
        is_small = row.get('Is_Small_Business', 'N')
        size = generate_size(name, is_small)
        revenue = generate_revenue(name)
        score = generate_score(name)
        
        # Tags
        tags = []
        if is_small == 'Y':
            tags.append('Small Business')
        if row.get('Is_Minority_Owned') == 'Y':
            tags.append('Minority Owned')
        if row.get('Is_Women_Owned') == 'Y':
            tags.append('Women Owned')
        if row.get('Is_Veteran_Owned') == 'Y':
            tags.append('Veteran Owned')
        if row.get('Is_SDVOSB') == 'Y':
            tags.append('SDVOSB')
        if row.get('Is_HUBZone') == 'Y':
            tags.append('HUBZone')
        if row.get('Is_8a_Program') == 'Y':
            tags.append('8a Program')
        if row.get('Is_Non_Profit') == 'Y':
            tags.append('Non-Profit')
        
        # fallback tags
        if not tags:
            tags = [row.get('Purpose_of_Registration', 'Federal Assistance').strip()]
            
        companies.append({
            "id": idx + 1,
            "uei": row.get('UEI', ''),
            "name": name,
            "industry": industry,
            "matchScore": score,
            "location": location,
            "size": size,
            "revenue": revenue,
            "status": status,
            "contact": contact,
            "email": email,
            "tags": tags[:3] # limit to 3 tags
        })

print(f"Total companies parsed: {len(companies)}")

# Ensure target directories exist
os.makedirs("Frontend/orbitavanya/public", exist_ok=True)
os.makedirs("Frontend/orbitavanya/src/data", exist_ok=True)

# Write full dataset to public/companies.json compactly (no indent)
with open("Frontend/orbitavanya/public/companies.json", 'w', encoding='utf-8') as out_f:
    json.dump(companies, out_f, separators=(',', ':'))

# Write first 500 companies to src/data/companies.js for initial/static load
subset = companies[:500]
with open("Frontend/orbitavanya/src/data/companies.js", 'w', encoding='utf-8') as out_js:
    out_js.write("export const companies = ")
    json.dump(subset, out_js, indent=2)
    out_js.write(";\n")

# Remove the temporary large JSON file from src/data if it exists
large_json = "Frontend/orbitavanya/src/data/companies.json"
if os.path.exists(large_json):
    os.remove(large_json)

print("Finished writing data files.")

