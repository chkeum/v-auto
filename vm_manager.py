#!/usr/bin/env python3
import argparse
import yaml
import os
import sys
import subprocess
import getpass
import copy
import ipaddress
from jinja2 import Environment, FileSystemLoader

# Force unverified SSL for self-signed clusters
import ssl
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECTS_DIR = os.path.join(BASE_DIR, 'projects')
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')

def run_command(cmd, input_data=None):
    """Executes a shell command and returns stdout."""
    try:
        result = subprocess.run(
            cmd,
            input=input_data,
            encoding='utf-8',
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        # print(f"DEBUG: Command failed: {e.stderr}")
        raise e

def load_yaml(path):
    if not os.path.exists(path):
        return {}
    with open(path, 'r') as f:
        return yaml.safe_load(f)

def load_config(project_name, spec_name):
    """
    Loads and merges configuration:
    1. Project Config (projects/<project>/config.yaml)
    2. VM Spec (projects/<project>/specs/<spec>.yaml)
    """
    project_path = os.path.join(PROJECTS_DIR, project_name, 'config.yaml')
    spec_path = os.path.join(PROJECTS_DIR, project_name, 'specs', f"{spec_name}.yaml")
    
    if not os.path.exists(project_path):
        print(f"Error: Project config not found at {project_path}")
        sys.exit(1)
    if not os.path.exists(spec_path):
        print(f"Error: VM Spec not found at {spec_path}")
        sys.exit(1)

    proj_conf = load_yaml(project_path)
    spec_conf = load_yaml(spec_path)
    
    # Context merging
    context = {}
    context.update(proj_conf) 
    context.update(spec_conf) # Spec overrides project
    
    # Handle Environment Variables in Auth
    if 'auth' in context:
        pwd = context['auth'].get('password', '')
        if pwd.startswith('env:'):
            env_var = pwd.split(':')[1]
            context['auth']['password'] = os.environ.get(env_var, '')
            if not context['auth']['password']:
                 print(f"Warning: Environment variable {env_var} is empty.")

    return context

def render_template(template_name, context):
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
    template = env.get_template(template_name)
    return template.render(context)

def get_network_config(entry, networks_catalog):
    """
    Resolves a network name from the catalog or returns the dict if it's already a dict.
    If it's a dict with a 'name' key, it merges with the catalog entry.
    """
    if isinstance(entry, dict):
        name = entry.get('name')
        if name and name in networks_catalog:
            # Merge catalog defaults with entry overrides
            conf = copy.deepcopy(networks_catalog[name])
            conf.update(entry)
            return conf
        return entry
    return networks_catalog.get(entry)

def discover_password_inputs(context):
    """
    Scans cloud_init for 'user:{{ var }}' patterns in chpasswd/list 
    to automatically identify which passwords to prompt for.
    """
    import re
    raw_ci = context.get('cloud_init', '')
    if not raw_ci: return []
    
    # regex to find 'username:{{ password_var }}'
    matches = re.findall(r'^\s*([^:\s]+):\{\{\s*(\w+)\s*\}\}', raw_ci, re.MULTILINE)
    
    discovered = []
    for user, key in matches:
        if key in ['username', 'interface_name', 'static_ip', 'gateway_ip']: continue
        
        discovered.append({
            'key': key,
            'prompt': f"Enter password for user '{user}'"
        })
    return discovered

def render_manifests(ctx):
    """Generates all K8s manifests for a VM instance."""
    manifests = []
    name = ctx['vm_name']
    project = ctx.get('project_name', 'default')
    spec = ctx.get('spec_name', 'default')
    
    # Standard Labels for Lifecycle Management
    labels = {
        'v-auto/managed': 'true',
        'v-auto/project': project,
        'v-auto/spec': spec,
        'v-auto/name': name
    }
    
    # 1. Secret (Cloud-Init)
    try:
        env = Environment()
        rendered_ci = env.from_string(ctx.get('cloud_init', '')).render(ctx)
        secret_context = ctx.copy()
        secret_context['cloud_init_content'] = rendered_ci
    except Exception as e:
        print(f"Error rendering cloud-init for {name}: {e}")
        sys.exit(1)
    
    secret = yaml.safe_load(render_template('secret_template.yaml', secret_context))
    secret.setdefault('metadata', {}).setdefault('labels', {}).update(labels)
    manifests.append(secret)
    
    # 2. NADs
    for idx, net in enumerate(ctx['interfaces']):
        nad_name = net.get('nad_name', f"{name}-net-{idx}")
        net['name'] = f"nic{idx}" 
        net['nad_ref'] = nad_name
        
        nad_ctx = ctx.copy()
        nad_ctx.update(net)
        nad_ctx['nad_name'] = nad_name
        
        if 'ipam' in nad_ctx and not isinstance(nad_ctx['ipam'], str):
            import json
            nad_ctx['ipam'] = json.dumps(nad_ctx['ipam'])
            
        if 'bridge' in net:
             nad = yaml.safe_load(render_template('nad_template.yaml', nad_ctx))
             nad.setdefault('metadata', {}).setdefault('labels', {}).update(labels)
             manifests.append(nad)
             
    # 3. DataVolume
    dv = yaml.safe_load(render_template('datavolume_template.yaml', ctx))
    dv.setdefault('metadata', {}).setdefault('labels', {}).update(labels)
    manifests.append(dv)
    
    # 4. VM
    vm = yaml.safe_load(render_template('vm_template.yaml', ctx))
    vm.setdefault('metadata', {}).setdefault('labels', {}).update(labels)
    # Also add labels to the template for VMI tracking
    vm.setdefault('spec', {}).setdefault('template', {}).setdefault('metadata', {}).setdefault('labels', {}).update(labels)
    manifests.append(vm)
    
    return manifests

def deploy_action(args):
    project = args.project
    spec = args.spec
    replicas_arg = args.replicas
    
    print(f"Loading configuration for Project: {project}, Spec: {spec}...")
    context = load_config(project, spec)
    
    # --- Interactive Inputs ---
    # 1. Discover from cloud-init (Dynamic Account Detection)
    discovered = discover_password_inputs(context)
    
    # 2. explicit inputs from config
    config_inputs = context.get('inputs', [])
    
    # 3. Merge: Prioritize discovered prompts if they match a key
    final_inputs = []
    seen_keys = set()
    
    # Map discovered for easy lookup
    discovered_map = { d['key']: d['prompt'] for d in discovered }
    
    for item in config_inputs:
        key = item['key']
        # If we discovered a specific account name for this key, use it
        if key in discovered_map:
            item['prompt'] = discovered_map[key]
        final_inputs.append(item)
        seen_keys.add(key)
        
    for d in discovered:
        if d['key'] not in seen_keys:
            final_inputs.append(d)
            seen_keys.add(d['key'])

    if not final_inputs and 'auth' in context:
         if not context['auth'].get('password'):
             final_inputs.append({'key': 'password', 'prompt': f"Password for {context['auth'].get('username', 'user')}"})

    if final_inputs:
        print("\n--- Required Inputs ---")
        for item in final_inputs:
            key = item.get('key')
            prompt_text = item.get('prompt', f"Enter value for '{key}'")
            if context.get(key): continue
            while True:
                val = getpass.getpass(f"{prompt_text}: ")
                if not val: continue
                val_confirm = getpass.getpass(f"Confirm {prompt_text}: ")
                if val != val_confirm:
                    print("Mismatch!"); continue
                context[key] = val
                break
        print("-----------------------\n")

    if 'password' in context:
        context.setdefault('auth', {})['password'] = context['password']
    
    # --- Determine Vars ---
    base_name = context.get('name_prefix', spec)
    replicas = replicas_arg if replicas_arg else context.get('replicas', 1)
    namespace = context.get('namespace', 'default')
    
    # --- Network Resolution ---
    # (Same logic as before, simpler lookup)
    proj_conf = load_yaml(os.path.join(PROJECTS_DIR, project, 'config.yaml'))
    catalog = proj_conf.get('networks', {})
    spec_networks = context.get('networks')
    final_net_list = []
    
    if isinstance(spec_networks, list):
        for net in spec_networks:
            final_net_list.append(get_network_config(net, catalog))
    elif isinstance(spec_networks, dict):
         final_net_list.append(catalog.get('default'))
    elif 'network' in context:
         final_net_list.append(get_network_config(context['network'], catalog))
    else: 
        final_net_list.append(catalog.get('default'))
        
    final_net_list = [n for n in final_net_list if n]
    if not final_net_list:
        print("Error: No valid networks resolving."); sys.exit(1)

    # --- Configuration Summary ---
    print("\n" + "="*50)
    print(f" [ Deployment Configuration Summary ] ")
    print("="*50)
    print(f" Project   : {project}")
    print(f" Spec      : {spec}")
    print(f" Namespace : {namespace}")
    print(f" Replicas  : {replicas}")
    print(f" Base Name : {base_name}")
    
    # Identify users for summary
    users = [d['prompt'].split("'")[1] for d in discovered]
    if not users:
        users = [context.get('auth', {}).get('username', 'N/A')]
    print(f" Users     : {', '.join(users)}")
    
    print(f" Image     : {context.get('image_url', 'N/A')}")
    print(f" Disk Size : {context.get('disk_size', 'N/A')}")
    print(f" StorageCls: {context.get('storage_class', 'N/A')}")
    print("-" * 50)
    print(" Network Interfaces:")
    for i, net in enumerate(final_net_list):
        net_type = net.get('type', 'multus')
        nad_name = net.get('nad_name', 'N/A')
        print(f"  NIC {i}: Type={net_type}, NAD={nad_name}")
    print("="*50 + "\n")
    
    if input("Proceed with dry-run/review? [Y/n]: ").lower() == 'n':
        print("Cancelled.")
        return

    # --- Replica Loop ---
    for i in range(replicas):
        suffix = f"-{i+1:02d}" if replicas > 1 else ""
        vm_name = f"{base_name}{suffix}"
        
        instance_ctx = context.copy()
        instance_ctx['vm_name'] = vm_name
        instance_ctx['project_name'] = project
        instance_ctx['spec_name'] = spec
        
        # Deep copy interfaces to modify them for this specific instance
        instance_interfaces = copy.deepcopy(final_net_list)
        
        # --- Automated Static IP Calculation ---
        # If IPAM range is present, we calculate a static IP based on replica index
        # to ensure consistency between NAD (K8s) and Cloud-Init (VM).
        for net in instance_interfaces:
            if 'ipam' in net and 'range' in net['ipam']:
                try:
                    cidr = net['ipam']['range']
                    gateway = net['ipam'].get('gateway')
                    
                    # Parse Network
                    network = ipaddress.IPv4Network(cidr, strict=False)
                    
                    # Logic: Start from .100 + index (e.g., 10.215.100.101 for replica 1)
                    # We assume the network is large enough.
                    # Verify gateway is not colliding.
                    
                    # Calculate target host offset
                    # 1-indexed loop 'i' counts 0,1. 
                    # Let's map i=0 -> .101, i=1 -> .102
                    host_offset = 101 + i 
                    
                    target_ip_obj = network.network_address + host_offset
                    target_ip = str(target_ip_obj)
                    
                    # Inject into NAD context (Switch to static IPAM for this instance)
                    # We override the type to 'static' so the NAD generated forces this IP.
                    # This replaces 'whereabouts' for this specific instance manifest.
                    net['ipam']['type'] = 'static'
                    net['ipam']['addresses'] = [{'address': f"{target_ip}/24"}] # Assuming /24, or derive from CIDR prefix len
                    # Actually better to derive prefix len
                    safe_cidr_suffix = str(network.prefixlen)
                    net['ipam']['addresses'] = [{'address': f"{target_ip}/{safe_cidr_suffix}"}]
                    # if gateway:
                    #     net['ipam']['gateway'] = gateway # Commented out as per instruction
                    # Only add specific routes if needed, avoid default route on secondary NIC
                    # net['ipam']['routes'] = [{"dst": "0.0.0.0/0", "gw": gateway}]
                    pass
                    
                    # Update NAD name to be instance-specific to avoid conflicts with static IP
                    orig_nad = net.get('nad_name', 'net')
                    net['nad_name'] = f"{vm_name}-{orig_nad}"
                    
                    # Inject variables for Cloud-Init (Jinja2)
                    instance_ctx['static_ip'] = f"{target_ip}/{safe_cidr_suffix}"
                    instance_ctx['gateway_ip'] = gateway
                    instance_ctx['interface_name'] = 'enp2s0' # Default assumption for 2nd NIC, can make configurable
                    
                    print(f"    [Auto-Net] Calculated Static IP: {target_ip} (GW: {gateway}, NAD: {net['nad_name']})")
                    
                except Exception as e:
                    print(f"    [Warning] Failed to calculate static IP: {e}")

        instance_ctx['interfaces'] = instance_interfaces
        
        print(f"\n>>> Preparing Replica {i+1}/{replicas}: {vm_name}")
        manifests = render_manifests(instance_ctx)
        
        # Dry Run Output
        print(f"\n[ Dry-Run: {vm_name} Manifests ]")
        for m in manifests:
            kind = m.get('kind', 'Unknown')
            m_name = m.get('metadata', {}).get('name', 'Unknown')
            print(f"\n--- Resource: {kind} / {m_name} ---")
            print(yaml.dump(m))
            
        # Confirm
        ans = input(f"\nCreate resources for {vm_name}? [y/N/q(uit)]: ").lower()
        if ans == 'q': return
        if ans != 'y': 
            print(f"Skipping {vm_name}."); continue
            
        # Apply
        print(f"Applying resources for {vm_name}...")
        for m in manifests:
            ignore = (m['kind'] == 'NetworkAttachmentDefinition')
            apply_k8s_resource(m, namespace, ignore_exists=ignore)
        print(f"--> {vm_name} Deployed.")

def apply_k8s_resource(manifest, namespace, ignore_exists=False):
    kind = manifest['kind']
    name = manifest['metadata']['name']
    
    cmd = ['oc', 'apply', '-f', '-', '-n', namespace]
    input_str = yaml.dump(manifest)
    
    try:
        run_command(cmd, input_data=input_str)
        print(f"  [SUCCESS] Created {kind}: {name}")
    except Exception as e:
        if ignore_exists:
            print(f"  [SKIPPED] {kind} {name} already exists.")
        else:
            print(f"  [FAILED ] {kind} {name}: {e}")

def delete_action(args):
    project = args.project
    spec = args.spec
    target = args.target
    
    context = load_config(project, spec)
    namespace = context.get('namespace', 'default')
    base_name = context.get('name_prefix', spec)
    
    selector = f"v-auto/project={project},v-auto/spec={spec}"
    if target: 
        selector = f"{selector},v-auto/name={target}"
    
    kinds = "vm,dv,secret,net-attach-def"
    
    # 1. Gather all targets
    print(f"Gathering resources for deletion in namespace '{namespace}'...")
    
    # Find by labels
    found_by_label = run_command(['oc', 'get', kinds, '-n', namespace, '-l', selector, '-o', 'name', '--ignore-not-found']).splitlines()
    found_by_label = [r for r in found_by_label if r.strip()]
    
    # Find by name prefix (Legacy Fallback)
    found_by_name = []
    if not target:
        all_res = run_command(['oc', 'get', 'vm,dv,secret', '-n', namespace, '-o', 'name', '--ignore-not-found']).splitlines()
        found_by_name = [r for r in all_res if r.split('/')[-1].startswith(base_name) and r.strip()]
        found_by_name = [r for r in found_by_name if r not in found_by_label]

    if not found_by_label and not found_by_name:
        print(f"\n[INFO] No matching resources found for Spec '{spec}' in {namespace}.")
        return

    print("\nTHE FOLLOWING RESOURCES WILL BE PERMANENTLY DELETED:")
    if found_by_label:
        print(f"\n--- Managed Resources (Selector: {selector}) ---")
        for r in found_by_label: 
            print(f"  {r}")
    if found_by_name:
        print(f"\n--- Legacy/Unmanaged (Matching Prefix: {base_name}-*) ---")
        for r in found_by_name: 
            print(f"  {r}")

    if input("\nAre you sure you want to proceed with deletion? [y/N]: ").lower() != 'y':
        print("Cancelled.")
        return

    # 2. Execution
    print("\nStarting deletion process...")
    
    # Delete labeled ones (Efficient bulk delete)
    if found_by_label:
        try:
            cmd = ['oc', 'delete', kinds, '-n', namespace, '-l', selector]
            run_command(cmd)
            print(f"  [SUCCESS] Managed resources deleted.")
        except Exception as e:
            print(f"  [FAILED ] Bulk deletion: {e}")
        
    # Delete name-based ones individually
    if found_by_name:
        for r in found_by_name:
            if "/" not in r: continue
            kind, name = r.split('/')
            try:
                run_command(['oc', 'delete', kind, name, '-n', namespace])
                print(f"  [DELETED] {kind}/{name}")
            except Exception as e:
                print(f"  [FAILED ] {kind}/{name}: {e}")

    print(f"\n[OK] Cleanup complete for Spec '{spec}'.")

def list_action(args):
    project = args.project
    spec = args.spec
    context = load_config(project, spec)
    ns = context.get('namespace', 'default')
    selector = f"v-auto/project={project},v-auto/spec={spec}"
    
    print(f"\n[ Summary List: {project}/{spec} ]")
    print(f"Namespace: {ns} | Selector: {selector}")
    print("-" * 70)
    
    # Simple table of all managed resource names/kinds
    managed = run_command(['oc', 'get', 'all,dv,secret,net-attach-def', '-n', ns, '-l', selector, '--ignore-not-found', '-o', 'custom-columns=KIND:.kind,NAME:.metadata.name,STATUS:.status.printableStatus,READY:.status.ready'])
    if not managed.strip() or "No resources found" in managed:
        print("   - No managed resources found.")
    else:
        print(managed)
    
    print("\n* Use 'status' command for detailed VM health and IP information.")
    print("-" * 70 + "\n")

def status_action(args):
    project = args.project
    spec = args.spec
    context = load_config(project, spec)
    ns = context.get('namespace', 'default')
    selector = f"v-auto/project={project},v-auto/spec={spec}"

    print(f"\n[ Detailed Status Diagnostic: {project}/{spec} ]")
    print(f"Target Namespace: {ns}")
    print("=" * 70)

    # 1. VM/VMI Detailed Status
    print("\n1. VM Instance Health & Networking")
    print("-" * 70)
    # Get VM and VMI details
    vms = run_command(['oc', 'get', 'vm', '-n', ns, '-l', selector, '--ignore-not-found', '-o', 'custom-columns=NAME:.metadata.name,STATUS:.status.printableStatus,READY:.status.ready,VOLUME_READY:.status.volumeRequests[*].type'])
    print(vms if vms.strip() else "   - No VMs found.")

    # Show active VMIs (for IP info)
    print("\n2. Active Runtime (VMI) & IPs")
    print("-" * 70)
    vmis = run_command(['oc', 'get', 'vmi', '-n', ns, '-l', selector, '--ignore-not-found', '-o', 'custom-columns=NAME:.metadata.name,PHASE:.status.phase,IP:.status.interfaces[0].ipAddress,NODE:.status.nodeName'])
    print(vmis if vmis.strip() else "   - No active VM instances (Running) found.")

    # 3. Storage (DataVolume) Progress
    print("\n3. Storage & Disk Provisioning (DataVolumes)")
    print("-" * 70)
    dvs = run_command(['oc', 'get', 'dv', '-n', ns, '-l', selector, '--ignore-not-found', '-o', 'custom-columns=NAME:.metadata.name,PHASE:.status.phase,PROGRESS:.status.progress,STORAGE_CLASS:.spec.storageClassName'])
    print(dvs if dvs.strip() else "   - No DataVolumes found.")

    # 4. Recent Events (Top 5)
    print("\n4. Recent Lifecycle Events (Top 5)")
    print("-" * 70)
    events = run_command(['oc', 'get', 'events', '-n', ns, '--sort-by=.lastTimestamp', '--ignore-not-found'])
    if events.strip():
        # Filter for our resources (crude grep)
        filtered_events = [line for line in events.splitlines() if spec in line or project in line][-5:]
        if filtered_events:
            for e in filtered_events: print(f"  {e}")
        else:
            print("   - No specific events for this spec recently.")
    else:
        print("   - No events found in namespace.")
    
    print("\n" + "=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="v-auto: High-Level OpenShift Virtualization Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Deploy a specific spec for a project
  python3 vm_manager.py samsung web deploy

  # Deploy with specific replica count and flag-based arguments
  python3 vm_manager.py --project samsung --spec db deploy --replicas 3

  # Delete all resources associated with a specific spec
  python3 vm_manager.py samsung web delete

  # Delete a specific VM instance only
  python3 vm_manager.py samsung web delete --target web-01

  # List current VMs and their status
  python3 vm_manager.py samsung web list
"""
    )
    
    # 1. Positional Arguments
    parser.add_argument('args_pos', nargs='*', metavar='project spec action', 
                        help="Positional arguments: [project] (e.g. samsung), [spec] (e.g. web), [action] (deploy|delete|list)")
    
    # 2. Flag-based Arguments (Highest Priority)
    group = parser.add_argument_group('Target Selection')
    group.add_argument('--vendor', '--project', dest='project_flag', 
                        help="Target project directory name in 'projects/'")
    group.add_argument('--spec', dest='spec_flag', 
                        help="VM specification file name in 'projects/[project]/specs/' (without .yaml)")
    group.add_argument('--action', dest='action_flag', 
                        choices=['deploy', 'delete', 'list', 'status'], 
                        help="Lifecycle action: 'deploy' (create), 'delete' (cleanup), 'list' (show status)")
    
    group_opt = parser.add_argument_group('Optional Overrides')
    group_opt.add_argument('--replicas', type=int, 
                           help="Override the default replica count defined in the spec YAML")
    group_opt.add_argument('--target', 
                           help="Specific VM instance name for granular deletion (e.g. web-02)")
    
    args = parser.parse_args()
    
    # 3. Intelligent Resolution Logic:
    project = args.project_flag
    spec = args.spec_flag
    action = args.action_flag
    
    # Map positional args to missing variables
    for p in args.args_pos:
        if not project:
            project = p
        elif not spec:
            spec = p
        elif not action and p in ['deploy', 'delete', 'list', 'status']:
            action = p
        elif not action:
            action = p

    if not project or not spec or not action or action not in ['deploy', 'delete', 'list', 'status']:
        parser.print_help()
        print("\n[ERROR] Missing or invalid arguments.")
        print("At least 'project', 'spec', and 'action' must be provided.")
        sys.exit(1)
        
    args.project = project
    args.spec = spec
    args.action = action
    
    if args.action == 'deploy':
        deploy_action(args)
    elif args.action == 'delete':
        delete_action(args)
    elif args.action in ['list', 'status']:
        list_action(args)

if __name__ == '__main__':
    main()
