import os
import csv

DOMAIN_ORDER = ['network', 'transport', 'session', 'presentation', 'protocols', 'wiring', 'application']
DOMAIN_NUMS = {'network': '0.1', 'transport': '0.2', 'session': '0.3', 'presentation': '0.4', 'protocols': '0.5', 'wiring': '0.6', 'application': '0.7'}

domains_csv = [{'element_number': DOMAIN_NUMS[d], 'element_name': d} for d in DOMAIN_ORDER]
subdomains_csv = []
files_csv = []

for domain in DOMAIN_ORDER:
    domain_num = DOMAIN_NUMS[domain]
    subdirs = []
    
    domain_path = 'src/' + domain
    if os.path.exists(domain_path):
        for item in os.listdir(domain_path):
            item_path = domain_path + '/' + item
            if os.path.isdir(item_path) and item not in ['__pycache__', '.obsolete', '.obsoletes', '.docs']:
                subdirs.append(item)
    
    subdirs.sort()
    
    # Domain level files (3-digit format: x.x.x.f)
    domain_files = [f for f in os.listdir(domain_path) if f.endswith('.py') or f.endswith('.yaml')]
    domain_files.sort()
    
    for file_idx, filename in enumerate(domain_files, 1):
        files_csv.append({
            'element_number': domain_num + '.' + str(file_idx) + '.f',
            'element_name': filename,
            'full_path': domain + '/' + filename
        })
    
    # Subdomain files (4-digit format: x.x.x.x.f)
    for sub_idx, subdir in enumerate(subdirs, 1):
        subdomains_csv.append({
            'element_number': domain_num + '.' + str(sub_idx),
            'element_name': subdir,
            'parent_domain': domain_num
        })
        
        sub_path = domain_path + '/' + subdir
        if os.path.exists(sub_path):
            files_in_sub = sorted([f for f in os.listdir(sub_path) if f.endswith('.py') or f.endswith('.yaml')])
            
            for file_idx, filename in enumerate(files_in_sub, 1):
                files_csv.append({
                    'element_number': domain_num + '.' + str(sub_idx) + '.' + str(file_idx) + '.f',
                    'element_name': filename,
                    'full_path': domain + '/' + subdir + '/' + filename
                })

# Write CSVs
with open('.docs/roadmap_to_full_production_ready/domains.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=['element_number', 'element_name'])
    writer.writeheader()
    writer.writerows(domains_csv)

with open('.docs/roadmap_to_full_production_ready/subdomains.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=['element_number', 'element_name', 'parent_domain'])
    writer.writeheader()
    writer.writerows(subdomains_csv)

with open('.docs/roadmap_to_full_production_ready/files.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=['element_number', 'element_name', 'full_path'])
    writer.writeheader()
    writer.writerows(files_csv)

print('Created CSVs with', len(files_csv), 'files')