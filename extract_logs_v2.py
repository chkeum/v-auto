import pexpect
import sys
import time

def extract_logs(vm_name='web-01'):
    print(f"Attempting to log in as core to extract logs from {vm_name}...")
    child = pexpect.spawn(f'virtctl console {vm_name} -n vm-opasnet', timeout=60)
    
    try:
        child.sendline('')
        child.expect(['login:', f'{vm_name} login:'], timeout=30)
        child.sendline('core')
        child.expect('Password:', timeout=10)
        child.sendline('core')
        
        # Wait for prompt
        child.expect([f'core@{vm_name}', '\\$'], timeout=20)
        print("Logged in. Extracting logs...")
        
        # Dump cloud-init output log
        child.sendline('sudo cat /var/log/cloud-init-output.log')
        child.expect([f'core@{vm_name}', '\\$'], timeout=30)
        print("\n--- /var/log/cloud-init-output.log ---")
        print(child.before.decode())
        
        # Dump cloud-init.log
        child.sendline('sudo cat /var/log/cloud-init.log | grep -i network')
        child.expect([f'core@{vm_name}', '\\$'], timeout=30)
        print("\n--- /var/log/cloud-init.log (network grep) ---")
        print(child.before.decode())

        # Check netplan files
        child.sendline('ls -l /etc/netplan/')
        child.expect([f'core@{vm_name}', '\\$'], timeout=10)
        print("\n--- /etc/netplan/ content ---")
        print(child.before.decode())
        
        child.sendline('logout')
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    vm = sys.argv[1] if len(sys.argv) > 1 else 'web-01'
    extract_logs(vm)
