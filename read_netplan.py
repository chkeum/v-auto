import pexpect
import sys
import time

def extract_logs(vm_name='web-01'):
    print(f"Attempting to log in as core to extract logs from {vm_name}...")
    child = pexpect.spawn(f'virtctl console {vm_name} -n vm-opasnet', timeout=120)
    
    try:
        # Send newlines to wake up console
        child.sendline('')
        time.sleep(2)
        child.sendline('')
        
        # Expect login prompt
        child.expect(['login:', f'{vm_name} login:'], timeout=60)
        child.sendline('core')
        child.expect('Password:', timeout=20)
        child.sendline('core')
        
        # Wait for prompt
        child.expect([f'core@{vm_name}', '\\$'], timeout=30)
        print("Logged in. Reading netplan file...")
        
        # Read netplan file
        child.sendline('sudo cat /etc/netplan/50-cloud-init.yaml')
        child.expect([f'core@{vm_name}', '\\$'], timeout=30)
        content = child.before.decode()
        print("\n--- /etc/netplan/50-cloud-init.yaml ---")
        print(content)
        
        # Check cloud-init status
        child.sendline('cloud-init status --wait')
        child.expect([f'core@{vm_name}', '\\$'], timeout=60)
        print("\n--- cloud-init status ---")
        print(child.before.decode())

        child.sendline('logout')
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    vm = sys.argv[1] if len(sys.argv) > 1 else 'web-01'
    extract_logs(vm)
