#!/usr/bin/python

"""
Minilab dynamic inventory script for ansible
Topology file must be defined in TOPOLOGY
environment variable.
"""

import sys
import argparse
import yaml
import os
import json

topology_file = os.environ.get('TOPOLOGY')

def load_config(config_file):
    cfg = open(config_file)
    config = yaml.load(cfg)
    cfg.close()

    return config

def get_inventory(topo):

    host_list = []

    for host in topo['hosts']:
        if 'is_manageable' in host:
            if host['is_manageable']:
                host_list.append(host['name'])

    inventory = {'manageables': {'hosts': host_list}}

    print json.dumps(inventory)


def get_host(hostname, topo):

    ansible_dict = {}
    oob_switch = topo['nat']['switch']['name']

    for host in topo['hosts']:
        host_iface_num = 0
        host_ifaces = []
        if host['name'] == hostname:
            ansible_dict['lab_hostname'] = hostname
            for link in host['links']:
                iface_name = "%s-eth%s" % (hostname, host_iface_num)
                host_ifaces.append(iface_name)

                if link['sw'] == oob_switch:
                    oob_ip = link['ip'].split("/")[0]
                    if 'ansible_host' not in ansible_dict:
                        ansible_dict['ansible_host'] = oob_ip

                host_iface_num += 1

            ansible_dict['ifaces'] = host_ifaces

            break

    print json.dumps(ansible_dict)

if __name__ == '__main__':

    try:
        topo_config = load_config(topology_file)
    except:
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Ansible dynamic inventory")
    parser.add_argument("--list", help="Ansible inventory of all of the groups",
                action="store_true", dest="list_inventory")
    parser.add_argument("--host", help="Ansible inventory of a particular host", action="store",
                dest="ansible_host", type=str)

    args = parser.parse_args()

    list_inventory = args.list_inventory
    ansible_host = args.ansible_host

    if list_inventory:
        get_inventory(topo_config)

    if ansible_host:
        get_host(ansible_host, topo_config)


