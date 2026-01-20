import pexpect
import sys
import time

def check_seed(vm_name='web-01'):
    print(f"Checking cloud-init seed on {vm_name}...")
    child = pexpect.spawn(f'virtctl console {vm_name} -n vm-opasnet', timeout=60)
    
    try:
        child.sendline('')
        # Try to expect either login or prompt
        idx = child.expect(['login:', 'Password:', f'{vm_name} login:', f'core@{vm_name}', '\\$'], timeout=30)
        
        if idx in [0, 2]:
            child.sendline('core')
            child.expect('Password:', timeout=10)
            child.sendline('core')
            child.expect([f'core@{vm_name}', '\\$'], timeout=20)
        elif idx == 1:
            child.sendline('core') # Assuming it wanted password for core? No, usually it's login.
            # If it's Password: maybe it's core?
            child.sendline('core')
            child.expect([f'core@{vm_name}', '\\$'], timeout=20)
        
        print("Logged in. Checking seed data...")
        
        # Check seed location
        child.sendline('ls -R /run/cloud-init/seed/')
        child.expect([f'core@{vm_name}', '\\$'], timeout=10)
        print("\n--- /run/cloud-init/seed/ content ---")
        print(child.before.decode())
        
        # Check network-config if it exists
        child.sendline('sudo cat /run/cloud-init/seed/nocloud-net/network-config')
        child.expect([f'core@{vm_name}', '\\$'], timeout=10)
        print("\n--- seed/network-config content ---")
        print(child.before.decode())

        # Check cloud-init userdata
        child.sendline('sudo cat /run/cloud-init/seed/nocloud-net/user-data | head -n 20')
        child.expect([f'core@{vm_name}', '\\$'], timeout=10)
        print("\n--- seed/user-data (partial) ---")
        print(child.before.decode())
        
        child.sendline('logout')
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    vm = sys.argv[1] if len(sys.argv) > 1 else 'web-01'
    check_seed(vm)
