
import re

def discover_password_inputs(raw_ci):
    discovered = []
    seen_keys = set()
    
    # 2. users list pattern: 
    #   - name: username
    #     passwd: {{ var | filter }}
    print(f"DEBUG: Splitting raw_ci (len={len(raw_ci)})")
    user_blocks = re.split(r'^\s*-\s*name:', raw_ci, flags=re.MULTILINE)
    print(f"DEBUG: Found {len(user_blocks)} blocks")
    
    for i, block in enumerate(user_blocks[1:]): # Skip text before the first '- name:'
        print(f"\n--- Block {i+1} ---")
        print(block.strip()[:50] + "...")
        
        # Get the username (first word of the block)
        name_match = re.match(r'^\s*([\w\-]+)', block)
        if not name_match: 
            print("DEBUG: No name match")
            continue
        username = name_match.group(1).strip()
        print(f"DEBUG: Username = {username}")
        
        # Look for password/passwd key in this specific user block, allowing pipe filters
        # Relaxed regex: {{\s*(\w+).*?}} matches any filter
        pass_match = re.search(r'^\s*pass(?:wd|word):\s*[\'"]?\{\{\s*(\w+).*?\}\}[\'"]?', block, re.MULTILINE)
        if pass_match:
            key = pass_match.group(1).strip()
            print(f"DEBUG: Found key = {key}")
            if key not in seen_keys:
                discovered.append({
                    'key': key,
                    'prompt': f"Enter password for user '{username}'"
                })
                seen_keys.add(key)
        else:
            print("DEBUG: No pass match")

    return discovered

raw = """
#cloud-config
ssh_pwauth: True
users:
  - name: opasnet-admin
    passwd: "{{ password | hash_password }}"
    ssh_authorized_keys:
      - ssh-rsa ...
    groups: [wheel]
  
  - name: dev-user
    passwd: "{{ dev_password | hash_password }}"
    groups: [wheel]
"""

print(discover_password_inputs(raw))
