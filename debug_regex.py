import re
import yaml

content = """
cloud_init: |
  #cloud-config
  chpasswd:
    list: |
      {{ username }}:{{ password }}
      dev-user:{{ dev_password }}
"""

data = yaml.safe_load(content)
raw_ci = data['cloud_init']

matches = re.findall(r'^\s*(.*?):\{\{\s*(\w+)\s*\}\}', raw_ci, re.MULTILINE)
print(f"Matches: {matches}")
