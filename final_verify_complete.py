import pexpect
import sys
import time

def verify_vm(vm_name, users_creds, expected_ips):
    print(f"\n>>>> Verifying {vm_name} <<<<")
    success = True
    
    # 5 minute timeout for boot
    child = pexpect.spawn(f'virtctl console {vm_name} -n vm-opasnet', timeout=300)
    # child.logfile_read = sys.stdout.buffer
    
    try:
        child.sendline('')
        # Wait for login prompt
        child.expect(['login:', 'web-01 login:', 'web-02 login:'], timeout=240)
        
        for username, password in users_creds:
            print(f"-- Testing {username} --")
            child.sendline(username)
            child.expect('Password:', timeout=20)
            child.sendline(password)
            i = child.expect(['login:', f'{username}@{vm_name}', '\\$'], timeout=30)
            
            if i == 0:
                print(f"[X] Login failed for {username}")
                success = False
                continue
                
            print(f"[V] {username} login successful.")
            
            # Check IPs
            for iface, ip in expected_ips:
                print(f"Checking {iface} for IP {ip}...")
                child.sendline(f'ip addr show {iface}')
                idx = child.expect([ip, f'{username}@{vm_name}'], timeout=10)
                if idx == 0:
                    print(f"[V] Interface {iface} has IP {ip}")
                else:
                    print(f"[X] Interface {iface} MISSING IP {ip}")
                    success = False
            
            child.sendline('logout')
            child.expect(['login:', 'web-01 login:', 'web-02 login:'], timeout=20)

        child.close(force=True)
        return success
    except Exception as e:
        print(f"[!] Critical failure for {vm_name}: {e}")
        child.close(force=True)
        return False

if __name__ == "__main__":
    print("Waiting 60 seconds for VMs to boot...")
    time.sleep(60)
    
    v1 = verify_vm('web-01', [('core', 'core'), ('suser', 'suser')], [('enp1s0', '10.215.100.101')])
    v2 = verify_vm('web-02', [('core', 'core')], [('enp1s0', '10.215.100.102'), ('enp2s0', '102.168.10.50')]) # wait, 192. vs 102. fix below
    
    # Correcting typo in check
    v2 = verify_vm('web-02', [('core', 'core')], [('enp1s0', '10.215.100.102'), ('enp2s0', '192.168.10.50')])

    if v1 and v2:
        print("\n[ALL GREEN] Both VMs verified successfully!")
        sys.exit(0)
    else:
        print("\n[RED] Verification failed for one or more VMs.")
        sys.exit(1)
