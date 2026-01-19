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
INFRA_DIR = os.path.join(BASE_DIR, 'infrastructure')
TEMPLATES_DIR = os.path.join(INFRA_DIR, 'templates') 

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
        # If command fails, we want to see the error from the tool (e.g. oc stderr)
        error_msg = e.stderr.strip() if e.stderr else str(e)
        raise Exception(error_msg)

def ensure_namespace(namespace):
    """Ensures the Kubernetes namespace exists."""
    try:
        run_command(['oc', 'get', 'namespace', namespace])
    except:
        print(f"  [INFO] Namespace '{namespace}' not found. Creating...")
        try:
            run_command(['oc', 'create', 'namespace', namespace])
            print(f"  [SUCCESS] Namespace '{namespace}' created.")
        except Exception as e:
            print(f"  [ERROR] Failed to create namespace '{namespace}': {e}")
            sys.exit(1)

def load_yaml(path):
    if not os.path.exists(path):
        return {}
    with open(path, 'r') as f:
        return yaml.safe_load(f)

def load_infrastructure_config(project_name, spec_context=None):
    """
    Loads infrastructure definitions.
    Priority 1: defined in Spec file (context['infrastructure'])
    Priority 2: defined in Project Infrastructure Directory (projects/<project>/infrastructure/*.yaml)
    """
    # 1. Start with Project-Level Files (Base)
    project_infra_dir = os.path.join(PROJECTS_DIR, project_name, 'infrastructure')
    
    infra = {
        'networks': {},
        'images': {},
        'storage_profiles': {}
    }

    if os.path.exists(project_infra_dir):
        infra['networks'] = load_yaml(os.path.join(project_infra_dir, 'networks.yaml')).get('networks', {})
        infra['images'] = load_yaml(os.path.join(project_infra_dir, 'images.yaml')).get('images', {})
        infra['storage_profiles'] = load_yaml(os.path.join(project_infra_dir, 'storage.yaml')).get('storage_profiles', {})
        
    # 2. Override/Merge with Spec-Level Definitions
    if spec_context and 'infrastructure' in spec_context:
        spec_infra = spec_context['infrastructure']
        
        # Merge Networks
        if 'networks' in spec_infra:
            infra['networks'].update(spec_infra['networks'])
            
        # Merge Images
        if 'images' in spec_infra:
            infra['images'].update(spec_infra['images'])
            
        # Merge Storage
        if 'storage_profiles' in spec_infra:
            infra['storage_profiles'].update(spec_infra['storage_profiles'])
            
    return infra

def load_config(project_name, spec_name):
    """
    Loads configuration (v1.0 Convention):
    1. Defaults (Namespace=vm-{project}, CPU=2, Mem=4Gi)
    2. VM Spec (projects/<project>/specs/<spec>.yaml) - Overrides defaults
    """
    spec_path = os.path.join(PROJECTS_DIR, project_name, 'specs', f"{spec_name}.yaml")
    
    if not os.path.exists(spec_path):
        print(f"Error: VM Spec not found at {spec_path}")
        sys.exit(1)

    spec_conf = load_yaml(spec_path)
    
    # 1. Convention Defaults
    context = {
        'namespace': f"vm-{project_name}",  # Convention: vm-<project>
        'cpu': 2,
        'memory': "4Gi",
        'disk_size': "50Gi",
        'auth': {} # Default empty, triggers interactive prompt if needed
    }
    
    # 2. Spec Overrides
    if 'common' in spec_conf:
        context.update(spec_conf['common'])
        context['instances'] = spec_conf.get('instances', [])
    else:
        context.update(spec_conf)
        
    # Always try to load cloud_init from root if not already in context
    if 'cloud_init' in spec_conf:
        context['cloud_init'] = spec_conf['cloud_init']
        
    # Always try to load infrastructure from root
    if 'infrastructure' in spec_conf:
        context['infrastructure'] = spec_conf['infrastructure']
    
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
    import json
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
    # Add json filter for complex objects like affinity
    env.filters['to_json'] = lambda v: json.dumps(v)
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
    Scans cloud_init for password variable patterns to automatically 
    identify which passwords to prompt for.
    Supports:
    1. chpasswd list style: 'username:{{ var }}'
    2. users list style: '- name: username' followed by 'passwd: {{ var }}'
    """
    import re
    raw_ci = context.get('cloud_init', '')
    if not raw_ci: return []
    
    discovered = []
    seen_keys = set()

    # 1. chpasswd pattern: 'username:{{ var }}'
    # Looks for 'user:{{ password_var }}' (ignoring filters if present, though chpasswd usually takes plain)
    chpasswd_matches = re.findall(r'^\s*([^:\s\-]+):\{\{\s*([\w]+)(?:\|[^}]+)?\s*\}\}', raw_ci, re.MULTILINE)
    for user, key in chpasswd_matches:
        if key in ['username', 'interface_name', 'static_ip', 'gateway_ip']: continue
        if key not in seen_keys:
            discovered.append({
                'key': key,
                'prompt': f"Enter password for user '{user}'"
            })
            seen_keys.add(key)

    # 2. users list pattern: 
    #   - name: username
    #     passwd: {{ var | filter }}
    user_blocks = re.split(r'^\s*-\s*name:', raw_ci, flags=re.MULTILINE)
    for block in user_blocks[1:]: # Skip text before the first '- name:'
        # Get the username (first word of the block)
        name_match = re.match(r'^\s*([\w\-]+)', block)
        if not name_match: continue
        username = name_match.group(1).strip()
        
        # Look for password/passwd key in this specific user block, allowing pipe filters
        pass_match = re.search(r'^\s*pass(?:wd|word):\s*[\'"]?\{\{\s*([\w]+)(?:\|[^}]+)?\s*\}\}[\'"]?', block, re.MULTILINE)
        if pass_match:
            key = pass_match.group(1).strip()
            if key not in seen_keys:
                discovered.append({
                    'key': key,
                    'prompt': f"Enter password for user '{username}'"
                })
                seen_keys.add(key)

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
        # Add password hashing filter
        import crypt
        def hash_password_filter(pwd):
            if not pwd: return ""
            return crypt.crypt(pwd, crypt.mksalt(crypt.METHOD_SHA512))
        env.filters['hash_password'] = hash_password_filter
        
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
    
    print(f"Loading configuration for Project: {project}, Spec: {spec}...")
    context = load_config(project, spec)
    infra_config = load_infrastructure_config(project, context)
    
    # --- Interactive Inputs (Auth) ---
    # Discover passwords from the common cloud-init context
    discovered = discover_password_inputs(context)
    
    # explicit inputs (legacy support)
    config_inputs = context.get('inputs', [])
    
    final_inputs = []
    seen_keys = set()
    discovered_map = { d['key']: d['prompt'] for d in discovered }
    
    for item in config_inputs:
        key = item['key']
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
    
    # --- Determine Instances ---
    instances = context.get('instances', [])
    if not instances:
        # Fallback to legacy 'replicas' logic if 'instances' not found
        replicas = args.replicas if args.replicas else context.get('replicas', 1)
        base_name = context.get('name_prefix', spec)
        print(f"[INFO] No 'instances' list found. Falling back to legacy replica mode (Count: {replicas})")
        for i in range(replicas):
            suffix = f"-{i+1:02d}" if (replicas > 1 or i > 0) else ""
            instances.append({
                'name': f"{base_name}{suffix}",
                # Legacy mode doesn't support explicit static IP per instance here easily
                # unless we rely on the old auto-calc logic.
                # For v2 refactor, we encourage 'instances' list.
            })
    
    namespace = context.get('namespace', 'default')
    
    # --- Network Resolution (Infra Catalog) ---
    catalog = infra_config['networks']
    
    # Resolve the "Common Network" defined in common block
    # e.g. network: svc-net
    common_net_name = context.get('network')
    # Or multiple networks
    common_networks = context.get('networks', [])

    # We need to construct the base interface list from common config
    base_interfaces = []
    
    if common_networks:
        if isinstance(common_networks, list):
            for net in common_networks:
                base_interfaces.append(get_network_config(net, catalog))
    elif common_net_name:
        base_interfaces.append(get_network_config(common_net_name, catalog))
    else: 
        # Default fallback
        base_interfaces.append(catalog.get('default'))
        
    base_interfaces = [n for n in base_interfaces if n]
    if not base_interfaces:
        print("Error: No valid networks resolving."); sys.exit(1)

    # --- Configuration Summary ---
    print("\n" + "="*50)
    print(f" [ Deployment Configuration Summary (v2.0) ] ")
    print("="*50)
    print(f" Project   : {project}")
    print(f" Spec      : {spec}")
    print(f" Namespace : {namespace}")
    print(f" Instances : {len(instances)}")
    for inst in instances:
        print(f"   - {inst['name']} (IP: {inst.get('ip', 'Auto/DHCP')})")
    
    # Identify users for summary
    users = [d['prompt'].split("'")[1] for d in discovered]
    if not users:
        users = [context.get('auth', {}).get('username', 'N/A')]
    print(f" Users     : {', '.join(users)}")
    
    # Image Resolution (Infra Catalog)
    image_key = context.get('image')
    image_url = context.get('image_url')
    if image_key and image_key in infra_config['images']:
        image_info = infra_config['images'][image_key]
        image_url = image_info['url']
        # Could also enforce min_cpu/mem here
        print(f" Image     : {image_key} (Resolved: {image_url})")
    else:
        print(f" Image     : {image_url} (Direct URL)")
    # Store resolved url in context
    context['image_url'] = image_url

    print(f" Disk Size : {context.get('disk_size', 'N/A')}")
    print(f" StorageCls: {context.get('storage_class', 'N/A')}")
    print("-" * 50)
    print(" Base Interfaces (Infra Managed):")
    for i, net in enumerate(base_interfaces):
        net_type = net.get('type', 'multus')
        nad_name = net.get('nad_name', 'N/A')
        print(f"  NIC {i}: Type={net_type}, NAD={nad_name}, Subnet={net.get('ipam', {}).get('range', 'N/A')}")
    print("="*50 + "\n")
    
    if not args.yes and not args.dry_run:
        if input("Proceed with dry-run/review? [Y/n]: ").lower() == 'n':
            print("Cancelled.")
            return

    # --- Ensure Namespace ---
    if not args.dry_run:
        ensure_namespace(namespace)

    # --- Instance Loop ---
    for inst in instances:
        vm_name = inst['name']
        
        # Target Filtering
        if args.target and args.target != vm_name:
            continue

        instance_ctx = context.copy()
        instance_ctx.update(inst) # Override common with instance specific (e.g. cpu, memory)
        instance_ctx['vm_name'] = vm_name
        instance_ctx['project_name'] = project
        instance_ctx['spec_name'] = spec
        
        # Determine Interfaces for this instance
        instance_interfaces = copy.deepcopy(base_interfaces)
        
        # --- Network Injection Logic ---
        # If instance has explicit 'ip', we find the matching interface and inject static IP config
        target_ip = inst.get('ip')
        if target_ip:
            # We assume the first non-pod network is the primary one to set static IP on
            # Or we could match by network name if provided in 'instances'. 
            # We apply to the first valid Multus interface found.
            injected = False
            for idx, net in enumerate(instance_interfaces):
                if net.get('type') == 'pod': continue
                
                # Verify IP belongs to subnet
                subnet_cidr = net.get('ipam', {}).get('range')
                gateway = net.get('ipam', {}).get('gateway')
                
                if subnet_cidr:
                    try:
                        network = ipaddress.IPv4Network(subnet_cidr, strict=False)
                        if ipaddress.IPv4Address(target_ip) not in network:
                            print(f"[WARNING] Instance {vm_name} IP {target_ip} is outside subnet {subnet_cidr}. Ignoring injection.")
                            continue
                            
                        # Correct logic: Inject Static IPAM type
                        safe_cidr_suffix = str(network.prefixlen)
                        net['ipam']['type'] = 'static'
                        net['ipam']['addresses'] = [{'address': f"{target_ip}/{safe_cidr_suffix}"}]
                        
                        # Generate Instance-Specific NAD Name
                        orig_nad = net.get('nad_name', 'net')
                        net['nad_name'] = f"{vm_name}-{orig_nad}"

                        # Cloud-Init Variables Injection
                        instance_ctx['static_ip'] = f"{target_ip}/{safe_cidr_suffix}"
                        instance_ctx['gateway_ip'] = gateway
                        
                        # Dynamic Interface Name Calculation (VirtIO convention: enp{idx+1}s0)
                        # nic0 -> enp1s0, nic1 -> enp2s0
                        instance_ctx['interface_name'] = f'enp{idx+1}s0' 
                        
                        print(f"    [Net-Inject] {vm_name}: Static IP {target_ip} on injected NAD {net['nad_name']} (Interface: {instance_ctx['interface_name']})")
                        injected = True
                        break # Only inject one primary IP for now
                    except Exception as e:
                        print(f"[ERROR] Invalid IP configuration: {e}")
            
            if not injected:
                 print(f"[WARNING] Could not inject Static IP {target_ip}. No matching subnet found in interfaces.")

        instance_ctx['interfaces'] = instance_interfaces
        
        print(f"\n>>> Preparing Instance: {vm_name}")
        manifests = render_manifests(instance_ctx)
        
        # Dry Run Output
        print(f"\n[ Dry-Run: {vm_name} Manifests ]")
        for m in manifests:
            kind = m.get('kind', 'Unknown')
            m_name = m.get('metadata', {}).get('name', 'Unknown')
            print(f"\n--- Resource: {kind} / {m_name} ---")
            print(yaml.dump(m))
            
        if args.dry_run:
            print(f" [Dry-Run] Skipping resource creation for {vm_name}.")
            continue

        if args.yes:
            ans = 'y'
        else:
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

    # Show final status
    print("\n" + "="*50)
    print(" [ Final Status Summary ]")
    print("="*50)
    status_action(args)

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
    
    kinds = "vm,dv,pvc,secret,net-attach-def"
    
    # 1. Gather all targets
    print(f"Gathering resources for deletion in namespace '{namespace}'...")
    
    # Find by labels
    found_by_label = run_command(['oc', 'get', kinds, '-n', namespace, '-l', selector, '-o', 'name', '--ignore-not-found']).splitlines()
    found_by_label = [r for r in found_by_label if r.strip()]
    
    # Find by name prefix (Legacy Fallback)
    found_by_name = []
    if not target:
        all_res = run_command(['oc', 'get', 'vm,dv,pvc,secret', '-n', namespace, '-o', 'name', '--ignore-not-found']).splitlines()
        found_by_name = [r for r in all_res if r.split('/')[-1].startswith(base_name) and r.strip()]
        found_by_name = [r for r in found_by_name if r not in found_by_label]

    if not found_by_label and not found_by_name:
        print(f"\n[INFO] No matching resources found for Spec '{spec}' in {namespace}.")
        return

    print("\nTHE FOLLOWING RESOURCES WILL BE PERMANENTLY DELETED:")
    if found_by_label:
        print(f"\n[ 1. Managed Resources (Selector: {selector}) ]")
        # Intelligent status: Use printableStatus if available, else Phase
        cols = "KIND:.kind,NAME:.metadata.name,STATUS:.status.printableStatus,PHASE:.status.phase,READY:.status.ready"
        table = run_command(['oc', 'get', kinds, '-n', namespace, '-l', selector, '-o', f'custom-columns={cols}'])
        clean_print_table(table, "Resources")
        
    if found_by_name:
        print(f"\n[ 2. Legacy/Unmanaged (Matching Prefix: {base_name}-*) ]")
        legacy_names = ",".join(found_by_name)
        cols = "KIND:.kind,NAME:.metadata.name,STATUS:.status.printableStatus,PHASE:.status.phase,READY:.status.ready"
        table = run_command(['oc', 'get', legacy_names, '-n', namespace, '-o', f'custom-columns={cols}', '--ignore-not-found'])
        clean_print_table(table, "Resources")

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
    
    # Show final status after deletion
    print("\n" + "="*50)
    print(" [ Final Status Summary ]")
    print("="*50)
    status_action(args)

def clean_print_table(output, title):
    """Prints oc output while replacing <none> with '-' for better readability."""
    if not output.strip() or "No resources found" in output:
        print(f"   - No {title.lower()} found.")
        return
    lines = output.strip().splitlines()
    if not lines: return
    print(lines[0])
    for line in lines[1:]:
        print(line.replace("<none>", "  -   "))

def status_action(args):
    project = args.project
    spec = args.spec
    context = load_config(project, spec)
    ns = context.get('namespace', 'default')
    selector = f"v-auto/project={project},v-auto/spec={spec}"
    if args.target:
        selector = f"{selector},v-auto/name={args.target}"

    target_info = f" (Target: {args.target})" if args.target else ""
    print(f"\n[ Detailed Status Diagnostic: {project}/{spec}{target_info} ]")
    print(f"Target Namespace: {ns}")
    print("=" * 100)

    try:
        # 1. Virtual Machines (Managed)
        print("\n1. Managed Virtual Machines (Health & Power)")
        print("-" * 100)
        vm_cols = "KIND:.kind,NAME:.metadata.name,STATUS:.status.printableStatus,READY:.status.ready"
        vms = run_command(['oc', 'get', 'vm', '-n', ns, '-l', selector, '--ignore-not-found', '-o', f'custom-columns={vm_cols}'])
        clean_print_table(vms, "Virtual Machines")

        # 2. Active Runtime & IP Addresses (VMI / Pod)
        print("\n2. Active Runtime & IP Addresses (VMI / Pod)")
        print("-" * 100)
        rt_cols = "KIND:.kind,NAME:.metadata.name,PHASE:.status.phase,VMI-IP:.status.interfaces[0].ipAddress,POD-IP:.status.podIP,NODE:.spec.nodeName"
        runtime_raw = run_command(['oc', 'get', 'vmi,pod', '-n', ns, '-l', selector, '--ignore-not-found', '-o', f'custom-columns={rt_cols}'])
        
        if not runtime_raw.strip() or "No resources found" in runtime_raw:
            print("   - No active runtimes found.")
        else:
            lines = runtime_raw.strip().splitlines()
            print(f"{'KIND':<25} {'NAME':<30} {'PHASE':<12} {'ADDRESS':<18} {'NODE'}")
            for line in lines[1:]:
                parts = line.split()
                if len(parts) < 3: continue
                kind, name, phase = parts[0], parts[1], parts[2]
                vmi_ip = parts[3] if len(parts) > 3 else "<none>"
                pod_ip = parts[4] if len(parts) > 4 else "<none>"
                node = parts[5] if len(parts) > 5 else "-"
                addr = vmi_ip if vmi_ip != "<none>" else (pod_ip if pod_ip != "<none>" else "-")
                print(f"{kind:<25} {name:<30} {phase:<12} {addr:<18} {node}")

        # 3. Storage Provisioning (DataVolume & PVC)
        print("\n3. Storage & Disk Provisioning (DataVolumes / PVC)")
        print("-" * 100)
        # DataVolume Status
        dv_cols = "KIND:.kind,NAME:.metadata.name,PHASE:.status.phase,PROGRESS:.status.progress"
        dvs = run_command(['oc', 'get', 'dv', '-n', ns, '-l', selector, '--ignore-not-found', '-o', f'custom-columns={dv_cols}'])
        clean_print_table(dvs, "DataVolumes")
        
        print("-" * 30)
        # PVC Status (Physical allocation)
        pvc_cols = "KIND:.kind,NAME:.metadata.name,STATUS:.status.phase,CAPACITY:.status.capacity.storage,ACCESS-MODES:.spec.accessModes"
        # Search by label first
        pvcs = run_command(['oc', 'get', 'pvc', '-n', ns, '-l', selector, '--ignore-not-found', '-o', f'custom-columns={pvc_cols}'])
        
        # If no labeled PVCs, try name prefix fallback
        if not pvcs.strip() or "No resources found" in pvcs:
            search_name = args.target if args.target else context.get('name_prefix', spec)
            # We fetch all PVCs and filter by name
            all_pvcs = run_command(['oc', 'get', 'pvc', '-n', ns, '-o', f'custom-columns={pvc_cols}', '--ignore-not-found'])
            if all_pvcs.strip() and "No resources found" not in all_pvcs:
                lines = all_pvcs.splitlines()
                header = lines[0]
                matched = [l for l in lines[1:] if l.split()[1].startswith(search_name)]
                if matched:
                    print(header)
                    for m in matched: print(m.replace("<none>", "  -   "))
                else:
                    print("   - No matching PVCs found.")
            else:
                print("   - No PVCs found.")
        else:
            clean_print_table(pvcs, "PVCs")

        # 4. Configuration & Network (NAD / Secret)
        print("\n4. Network (NAD) & Config (Secret) Resources")
        print("-" * 100)
        cfg_cols = "KIND:.kind,NAME:.metadata.name,CREATED:.metadata.creationTimestamp"
        configs = run_command(['oc', 'get', 'net-attach-def,secret', '-n', ns, '-l', selector, '--ignore-not-found', '-o', f'custom-columns={cfg_cols}'])
        clean_print_table(configs, "Config Resources")

        # 5. Recent Events (Intelligent Diagnostics)
        print("\n5. Recent Events (Priority: Warning first, Max 15)")
        print("-" * 100)
        events_raw = run_command(['oc', 'get', 'events', '-n', ns, '--sort-by=.lastTimestamp', '--ignore-not-found'])
        if events_raw.strip():
            base_name = context.get('name_prefix', spec)
            lines = events_raw.splitlines()
            
            # Filter: Only events related to this spec/base_name/target
            # If target is provided, we strictly filter by target name to avoid noise from other instances
            search_term = args.target if args.target else spec
            relevant = [l for l in lines if search_term in l or base_name in l]
            
            # If specific target, ensure it's actually about that target (more strict)
            if args.target:
                relevant = [l for l in relevant if args.target in l]
            
            if relevant:
                # Prioritize: Warning events go to top, then Normal
                warnings = [l for l in relevant if "Warning" in l]
                normals = [l for l in relevant if "Normal" in l]
                
                # Combine and limit to 15
                final_list = (warnings + normals)[-15:]
                
                print(f"{'AGE':<10} {'TYPE':<8} {'REASON':<15} {'OBJECT':<40} {'MESSAGE'}")
                for e in final_list:
                    p = e.split()
                    if len(p) < 5: continue
                    # AGE(0), TYPE(1), REASON(2), OBJECT(3), MESSAGE(4...)
                    age, etype, reason, obj = p[0], p[1], p[2], p[3]
                    msg = " ".join(p[4:])
                    # Truncate object name if too long to keep table aligned
                    if len(obj) > 38: obj = obj[:35] + "..."
                    print(f"{age:<10} {etype:<8} {reason:<15} {obj:<40} {msg}")
            else:
                print("   - No specific events found for this spec recently.")
        else:
            print("   - No events found in namespace.")
    except Exception as e:
        print(f"\n[WARNING] Could not retrieve full status summary: {e}")
        print("This may be expected if resources are still being created or if permissions are restricted.")
    
    print("\n" + "=" * 100 + "\n")

# Aliasing list to status for backward compatibility, though user suggested status only.
def list_action(args):
    status_action(args)


def inspect_action(args):
    """Prints the effective configuration for the project/spec."""
    project = args.project
    spec = args.spec
    
    print(f"\nExample: Inspecting Config for [{project}/{spec}]")
    print("=" * 60)
    
    # 1. Load Context (Convention + Spec)
    try:
        context = load_config(project, spec)
        print(f" [1] Effective Context (Namespace: {context.get('namespace')})")
        print(f"     - Resources: CPU={context.get('cpu')}, Mem={context.get('memory')}, Disk={context.get('disk_size')}")
        print(f"     - Instances ({len(context.get('instances', []))}):")
        for inst in context.get('instances', []):
            print(f"       * {inst['name']} (IP: {inst.get('ip', 'Auto')})")
            
        # Cloud-Init Summary
        ci_raw = context.get('cloud_init', '')
        if ci_raw:
            print(f"     - Cloud-Init (Summary):")
            try:
                # Attempt to parse YAML to show details
                ci_data = yaml.safe_load(ci_raw)
                
                # Users
                users = ci_data.get('users', [])
                user_names = [u.get('name', 'unknown') for u in users]
                print(f"       * Users: {', '.join(user_names)}")
                
                # Packages
                pkgs = ci_data.get('packages', [])
                if pkgs:
                    print(f"       * Packages: {len(pkgs)} items")
                
                # RunCmd
                cmds = ci_data.get('runcmd', [])
                if cmds:
                    print(f"       * RunCmd: {len(cmds)} commands")
            except:
                print(f"       * (Template content detected, raw size: {len(ci_raw)} bytes)")
                
    except Exception as e:
        print(f" [ERROR] Failed to load spec: {e}")
        return

    # 2. Load Infrastructure
    print("-" * 60)
    infra = load_infrastructure_config(project, context)
    
    print(f" [2] Infrastructure Catalog (projects/{project}/infrastructure/)")
    
    nets = infra.get('networks', {})
    print(f"     - Networks ({len(nets)}):")
    if not nets:
        print("       (None defined. Create networks.yaml to add)")
    for name, details in nets.items():
        # Short summary of network
        nads = details.get('nad_name', details.get('nad', 'N/A'))
        if details.get('type') == 'pod':
            nads = '(Pod Network)'
        print(f"       * {name:<15} -> NAD: {nads}")

    imgs = infra.get('images', {})
    print(f"     - Images ({len(imgs)}):")
    if not imgs:
        print("       (None defined. Create images.yaml to add)")
    for name, details in imgs.items():
        src = details.get('pvc_name')
        if not src:
            src = details.get('url', 'N/A') # Show URL if PVC not found
        else:
            src = f"PVC:{src}"
            
        print(f"       * {name:<15} -> Source: {src}")
        
    print("=" * 60)
    print("Ready to deploy? Run with 'deploy' action.\n")

def main():
    parser = argparse.ArgumentParser(
        description="v-auto: High-Level OpenShift Virtualization Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Deploy a specific spec for a project
  python3 vm_manager.py opasnet web deploy

  # Deploy with specific replica count and flag-based arguments
  python3 vm_manager.py --project opasnet --spec db deploy --replicas 3

  # Deploy/Recover a specific VM instance only
  python3 vm_manager.py opasnet web deploy --target web-02

  # Delete all resources associated with a specific spec
  python3 vm_manager.py opasnet web delete

  # Delete a specific VM instance only
  python3 vm_manager.py opasnet web delete --target web-01

  # List current VMs and their status
  python3 vm_manager.py opasnet web status

  # Check status of a specific VM instance
  python3 vm_manager.py opasnet web status --target web-01
"""
    )
    
    # 1. Positional Arguments
    parser.add_argument('args_pos', nargs='*', metavar='project spec action', 
                        help="Positional arguments: [project] (e.g. opasnet), [spec] (e.g. web), [action] (deploy|delete|status)")
    
    # 2. Flag-based Arguments (Highest Priority)
    group = parser.add_argument_group('Target Selection')
    group.add_argument('--project', dest='project_flag', 
                        help="Target project directory name in 'projects/'")
    group.add_argument('--spec', dest='spec_flag', 
                        help="VM specification file name in 'projects/[project]/specs/' (without .yaml)")
    group.add_argument('--action', dest='action_flag', 
                        choices=['deploy', 'delete', 'status', 'inspect'], 
                        help="Lifecycle action: 'deploy', 'delete', 'status', 'inspect'")
    
    group_opt = parser.add_argument_group('Optional Overrides')
    group_opt.add_argument('--replicas', type=int, 
                           help="Override the default replica count defined in the spec YAML")
    group_opt.add_argument('--target', 
                           help="Specific VM instance name for granular action (e.g. web-02)")
    group_opt.add_argument('--yes', '-y', action='store_true',
                           help="Skip interactive confirmations (Automated mode)")
    group_opt.add_argument('--dry-run', action='store_true',
                           help="Render manifests without applying them")
    
    args = parser.parse_args()
    
    # 3. Intelligent Resolution Logic:
    project = args.project_flag
    spec = args.spec_flag
    action = args.action_flag
    
    # Pre-scan positional args for action keywords to avoid mis-mapping
    action_keywords = ['deploy', 'delete', 'list', 'status', 'inspect']
    for p in args.args_pos:
        if p in action_keywords and not action:
            action = p
            break

    # Map remaining positional args to missing variables
    for p in args.args_pos:
        if p == action: continue # Already mapped
        if not project:
            project = p
        elif not spec:
            spec = p

    # Validation & Enhanced Error Reporting
    missing = []
    if not project: missing.append("project (e.g. opasnet)")
    if not spec: missing.append("spec (e.g. web)")
    if not action: missing.append("action (deploy, delete, status, inspect)")

    if missing:
        parser.print_usage()
        print(f"\n[ERROR] Missing required arguments: {', '.join(missing)}")
        
        # Intelligent Hint
        if args.target and not action:
            print("\n[HINT] You provided '--target' but no action. Did you mean 'delete'?")
            print(f"       Try: python3 vm_manager.py {project or '<project>'} {spec or '<spec>'} delete --target {args.target}")
        
        print("\nRun with '-h' for full help and examples.")
        sys.exit(1)
        
    if action not in action_keywords:
        print(f"\n[ERROR] Invalid action '{action}'. Choose from: {', '.join(action_keywords)}")
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
    elif args.action == 'inspect':
        inspect_action(args)

if __name__ == '__main__':
    main()
