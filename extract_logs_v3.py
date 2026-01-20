import pexpect
import sys
import time

def extract_logs(vm_name='web-01'):
    print(f"Attempting to log in as core to extract logs from {vm_name}...")
    child = pexpect.spawn(f'virtctl console {vm_name} -n vm-opasnet', timeout=120)
    # child.logfile_read = sys.stdout.buffer
    
    try:
        # Send a few newlines to wake up the console
        for _ in range(5):
            child.sendline('')
            time.sleep(1)
            
        # Expect login prompt or password prompt (if login was somehow pre-filled)
        idx = child.expect(['login:', 'Password:', f'{vm_name} login:'], timeout=60)
        
        if idx == 1:
            # Somehow at password prompt, let's try 'core' just in case
            child.sendline('core')
            child.expect(['login:', 'Password:', f'{vm_name} login:'], timeout=20)
            # if still at password, maybe it was core? try core again
            child.sendline('core')
        else:
            child.sendline('core')
            child.expect('Password:', timeout=20)
            child.sendline('core')
        
        # Wait for prompt
        child.expect([f'core@{vm_name}', '\\$'], timeout=30)
        print("Logged in. Extracting logs...")
        
        # Dump cloud-init output log
        child.sendline('sudo cat /var/log/cloud-init-output.log')
        child.expect([f'core@{vm_name}', '\\$'], timeout=60)
        print("\n--- /var/log/cloud-init-output.log ---")
        print(child.before.decode())
        
        # Dump cloud-init.log
        child.sendline('sudo cat /var/log/cloud-init.log | grep -i network')
        child.expect([f'core@{vm_name}', '\\$'], timeout=60)
        print("\n--- /var/log/cloud-init.log (network grep) ---")
        print(child.before.decode())

        # Check netplan files
        child.sendline('ls -l /etc/netplan/')
        child.expect([f'core@{vm_name}', '\\$'], timeout=10)
        print("\n--- /etc/netplan/ content ---")
        print(child.before.decode())

        child.sendline('cat /etc/netplan/*.yaml')
        child.expect([f'core@{vm_name}', '\\$'], timeout=10)
        print("\n--- /etc/netplan/*.yaml content ---")
        print(child.before.decode())
        
        child.sendline('logout')
        return True
    except Exception as e:
        print(f"Error: {e}")
        # Try to capture what was on screen
        print("Screen content before error:")
        print(child.before.decode() if child.before else "None")
        return False

if __name__ == "__main__":
    vm = sys.argv[1] if len(sys.argv) > 1 else 'web-01'
    extract_logs(vm)
