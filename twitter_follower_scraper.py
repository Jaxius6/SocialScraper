import sys
import subprocess
import datetime
import pandas as pd

def install_requirements():
    """Install required packages if they're missing."""
    required_packages = [
        'selenium',
        'requests',
        'webdriver-manager',
        'pandas'
    ]
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            print(f"Installing {package}...")
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])
            print(f"Successfully installed {package}")

# Install requirements if needed
if __name__ == '__main__':
    install_requirements()

# Now import all required packages
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import time
import random
import requests
import json
import re

# Airtable configuration
AIRTABLE_PAT = "patC3CJ296jcbbAMd.e12065cdff24c5b8e6ed1e9315fa4f5a9233ee9803efd602a7a2a74ff14c5057"
AIRTABLE_BASE_ID = "appdeZcAttBaG5oVI"
AIRTABLE_TABLE_NAME = "Politicians"

def wait_random():
    time.sleep(random.uniform(0.2, 0.5))  # Quick wait

def parse_follower_count(text):
    try:
        # Remove any non-numeric characters except commas, decimal points, and K/M/B
        text = text.strip()
        # Extract just the number part if it's in a format like "2,771 Followers" or "100K Followers"
        number_match = re.search(r'([\d,\.]+\s*[KMBkmb]?)\s*(?:Followers?)?', text)
        if number_match:
            number_str = number_match.group(1).strip()
            
            # Handle K, M, B suffixes
            multiplier = 1
            if number_str[-1].upper() == 'K':
                multiplier = 1000
                number_str = number_str[:-1]
            elif number_str[-1].upper() == 'M':
                multiplier = 1000000
                number_str = number_str[:-1]
            elif number_str[-1].upper() == 'B':
                multiplier = 1000000000
                number_str = number_str[:-1]
            
            # Remove commas and convert to float
            number_str = number_str.replace(',', '')
            return float(number_str) * multiplier
    except Exception as e:
        print(f"Error parsing follower count '{text}': {str(e)}")
    return None

def get_follower_counts(usernames, max_retries=3):
    # Setup Chrome options
    options = webdriver.ChromeOptions()
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    results = []
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    driver = None
    
    try:
        print("Initializing Chrome driver...")
        # Use a more reliable way to initialize Chrome
        try:
            service = Service()
            driver = webdriver.Chrome(service=service, options=options)
        except Exception as e:
            print(f"Error with default service, trying ChromeDriverManager: {str(e)}")
            try:
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=options)
            except Exception as e:
                print(f"Error with ChromeDriverManager: {str(e)}")
                # Try one more time with default Chrome location
                service = Service("chromedriver.exe")
                driver = webdriver.Chrome(service=service, options=options)
        
        driver.set_page_load_timeout(10)  # 10 second timeout
        
        for username in usernames:
            retries = 0
            follower_count = None
            
            while retries < max_retries:
                try:
                    print(f"\nProcessing @{username} (attempt {retries + 1})...")
                    url = f'https://twitter.com/{username}'
                    
                    try:
                        driver.get(url)
                        
                        # Try to grab data as soon as we see any content
                        for _ in range(5):  # Try up to 5 quick attempts
                            try:
                                # Check for redirect
                                if not driver.current_url.lower().endswith(username.lower()):
                                    raise Exception("Redirect detected")
                                
                                # Quick check for any content
                                page_info = driver.execute_script(r"""
                                    function findFollowers() {
                                        let results = [];
                                        try {
                                            // Function to clean and validate text
                                            function isValidFollowerText(text) {
                                                text = text.trim();
                                                // Allow for K, M, B suffixes before "Followers"
                                                return /^\d[\d,\.]*\s*[KMBkmb]?\s+Followers$/.test(text);
                                            }

                                            // Special handling for protected profiles
                                            const allElements = document.querySelectorAll('*');
                                            for (const elem of allElements) {
                                                if (elem.tagName.toLowerCase() === 'span' || elem.tagName.toLowerCase() === 'div') {
                                                    const text = elem.textContent.trim();
                                                    // Look for numbers with optional K/M/B suffix
                                                    if (/^[\d,\.]+\s*[KMBkmb]?$/.test(text)) {
                                                        const nextElem = elem.nextElementSibling;
                                                        if (nextElem && nextElem.textContent.trim() === 'Followers') {
                                                            results.push({
                                                                text: text + ' Followers',
                                                                type: 'protected-stats'
                                                            });
                                                        }
                                                    }
                                                }
                                            }

                                            // If we haven't found anything, try the regular profile selectors
                                            if (results.length === 0) {
                                                // Try finding the followers link (not following)
                                                const followerLinks = document.querySelectorAll('a[href$="/followers"]');
                                                for (const link of followerLinks) {
                                                    const text = link.textContent.trim();
                                                    if (isValidFollowerText(text)) {
                                                        results.push({
                                                            text: text,
                                                            type: 'link'
                                                        });
                                                    }
                                                }

                                                // Look for specific number spans
                                                const elements = document.querySelectorAll('span[dir="ltr"]');
                                                let foundFollowing = false;
                                                for (const elem of elements) {
                                                    const text = elem.textContent.trim();
                                                    if (/^\d[\d,\.]*$/.test(text)) {
                                                        // Check if this is part of the stats section
                                                        const parent = elem.parentElement;
                                                        const nextElem = elem.nextElementSibling;
                                                        
                                                        // Skip if this is the "Following" count
                                                        if (nextElem && nextElem.textContent.trim() === 'Following') {
                                                            foundFollowing = true;
                                                            continue;
                                                        }
                                                        
                                                        // If we found Following before, this should be Followers
                                                        if (foundFollowing && nextElem && nextElem.textContent.trim() === 'Followers') {
                                                            results.push({
                                                                text: text + ' Followers',
                                                                type: 'stats'
                                                            });
                                                        }
                                                    }
                                                }
                                            }

                                        } catch (e) {
                                            console.error('Error finding followers:', e);
                                        }
                                        return JSON.stringify(results);
                                    }
                                    return findFollowers();
                                """)
                                
                                if page_info:
                                    elements = json.loads(page_info)
                                    if elements:
                                        print(f"\nFound {len(elements)} potential elements:")
                                        for element in elements:
                                            print("Element:", element)
                                            if 'text' in element:
                                                count = parse_follower_count(element['text'])
                                                if count is not None:
                                                    follower_count = count
                                                    print(f"\nExtracted follower count: {count:,.0f}")
                                                    raise StopIteration  # Break out of all loops
                                
                                time.sleep(0.5)  # Short wait between quick attempts
                                
                            except StopIteration:
                                break  # Found the count, exit the quick attempt loop
                            except Exception as e:
                                if "Redirect detected" in str(e):
                                    raise  # Re-raise redirect exception
                                print(f"Quick attempt error: {str(e)}")
                        
                        # If we haven't found the count, wait for full page load
                        if follower_count is None:
                            wait = WebDriverWait(driver, 5)
                            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-testid="primaryColumn"]')))
                            time.sleep(2)
                            
                    except Exception as e:
                        print(f"Page load/redirect error: {str(e)}")
                        retries += 1
                        if retries < max_retries:
                            print(f"Retrying in 10 seconds... (attempt {retries + 1})")
                            time.sleep(10)
                        continue
                    
                    if follower_count is not None:
                        results.append({
                            'username': username,
                            'follower_count': follower_count,
                            'timestamp': timestamp
                        })
                        break  # Successfully got the count, no need for more retries
                    
                    retries += 1
                    if retries < max_retries:
                        print(f"\nNo follower count found. Waiting 10 seconds before retry... (attempt {retries + 1})")
                        time.sleep(10)
                        
                except Exception as e:
                    print(f"Error in attempt {retries + 1}: {str(e)}")
                    retries += 1
                    if retries < max_retries:
                        print(f"\nRetrying in 10 seconds... (attempt {retries + 1})")
                        time.sleep(10)
            
            if follower_count is None:
                print(f"\nFailed to get follower count for @{username} after {max_retries} attempts")
                results.append({
                    'username': username,
                    'follower_count': None,
                    'timestamp': timestamp
                })
    
    finally:
        if driver:
            driver.quit()
    
    return results

def get_airtable_records():
    """Fetch records from Airtable."""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_PAT}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        records = response.json().get('records', [])
        return [(record['id'], record['fields'].get('twitter_user', '')) 
                for record in records 
                if record['fields'].get('twitter_user')]
    except Exception as e:
        print(f"Error fetching from Airtable: {str(e)}")
        return []

def update_airtable_batch(updates):
    """Update multiple records in Airtable in a single request."""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_PAT}",
        "Content-Type": "application/json"
    }
    
    records = [{"id": record_id, "fields": {"twitter_followers": count}} 
               for record_id, count in updates]
    
    data = {
        "records": records
    }
    
    try:
        response = requests.patch(url, headers=headers, json=data)
        response.raise_for_status()
        print(f"Successfully updated batch of {len(updates)} records")
        return True
    except Exception as e:
        print(f"Error updating batch in Airtable: {str(e)}")
        return False

if __name__ == "__main__":
    print("Fetching Twitter usernames from Airtable...")
    airtable_records = get_airtable_records()  # Get all records
    
    if not airtable_records:
        print("No Twitter usernames found in Airtable.")
        exit()
    
    print(f"Found {len(airtable_records)} Twitter accounts to process...")
    usernames = [username for _, username in airtable_records]
    print("Processing usernames:", ", ".join(f"@{username}" for username in usernames))
    print("\nStarting the scraping process...")
    
    results = get_follower_counts(usernames)
    
    # Prepare updates in batches of 10
    print("\nUpdating Airtable with follower counts...")
    updates = []
    success_count = 0
    batch_size = 10
    
    for result, (record_id, _) in zip(results, airtable_records):
        count = result['follower_count']
        if count is not None:
            updates.append((record_id, int(count)))
            
            # Process batch when it reaches size 10 or at the end
            if len(updates) >= batch_size:
                if update_airtable_batch(updates):
                    success_count += len(updates)
                updates = []
    
    # Process any remaining updates
    if updates:
        if update_airtable_batch(updates):
            success_count += len(updates)
    
    # Separate successful and failed results
    successful_results = []
    failed_results = []
    
    for result in results:
        if result['follower_count'] is not None:
            successful_results.append(result)
        else:
            failed_results.append(result)
    
    # Print results in a nice format
    print("\nFinal Results:")
    print("-" * 50)
    
    if successful_results:
        print("\nSuccessful Updates:")
        for result in successful_results:
            count = result['follower_count']
            print(f"@{result['username']}: {count:,.0f} followers")
    
    if failed_results:
        print("\nFailed Updates:")
        for result in failed_results:
            print(f"@{result['username']}: Not found")
    
    print(f"\nTimestamp: {results[0]['timestamp']}")
    print(f"Successfully updated {success_count} out of {len(results)} records in Airtable")
    if failed_results:
        print(f"Failed to get follower counts for {len(failed_results)} accounts")
