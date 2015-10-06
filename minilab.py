#!/usr/bin/python

"""
Minilab is a network lab simulator based on
mininet. Its goal is to provide an easy way
to setup and test any kind of complex network.

"""

import sys
import subprocess
import shlex
import argparse
import yaml
import os

from mininet.net import Mininet
from mininet.node import Host, OVSSwitch, RemoteController
from mininet.log import setLogLevel, info
from mininet.cli import CLI

from jinja2 import FileSystemLoader, Environment

from nat import *


class ManageableHost(Host):
    def __init__(self, name, ip=None, inNamespace=True,
                 labdir='/var/minilab', root_fs=None,
                 ssh_template=None, auth_keys=None):

        self.name = name
        self.root_fs = root_fs
        self.lab_dir = labdir
        self.ssh_template = ssh_template
        self.auth_keys = auth_keys
        self.root_dir = None
        self.ssh_pid_file = None
        self.mounted_dirs = []

        super(Host, self).__init__(name, ip=None, inNamespace=True)

    def list_processes(self):
        pass

    def stop_processes(self):
        self.stop_ssh_server()

    def mount_root_fs(self):
        if not os.path.exists(self.lab_dir):
            os.mkdir(self.lab_dir)

        host_dir = os.path.join(self.lab_dir, self.name)
        work_dir = os.path.join(host_dir, 'work')
        upper_dir = os.path.join(host_dir, 'upper')
        merged_dir = os.path.join(host_dir, 'merged')

        if not os.path.exists(host_dir):
            os.mkdir(host_dir)
            os.mkdir(work_dir)
            os.mkdir(upper_dir)
            os.mkdir(merged_dir)

        cmd = "mount -t overlay overlay -o lowerdir=%s,upperdir=%s,workdir=%s %s" % \
              (self.root_fs, upper_dir, work_dir, merged_dir)

        mount_root = shlex.split(cmd)
        subprocess.call(mount_root)

        host_proc = os.path.join(merged_dir, 'proc')
        cmd_p = "mount -t proc proc %s" % host_proc
        mount_proc = shlex.split(cmd_p)
        subprocess.call(mount_proc)
        self.mounted_dirs.append(host_proc)

        host_sys = os.path.join(merged_dir, 'sys')
        cmd_s = "mount -t sysfs sysfs %s" % host_sys
        mount_sys = shlex.split(cmd_s)
        subprocess.call(mount_sys)
        self.mounted_dirs.append(host_sys)

        self.root_dir = merged_dir
        self.mounted_dirs.append(merged_dir)

    def umount_root_fs(self):
        for mount_point in self.mounted_dirs:
            subprocess.call(shlex.split("umount %s" % mount_point))

        # fixme: currently need to umount /sys
        subprocess.call(shlex.split("umount %s" % '/sys'))

    def create_ssh_config(self):
        self.ssh_pid_file = os.path.join(self.lab_dir, self.name, "sshd.pid")

        return self.ssh_template.render(pid_file=self.ssh_pid_file,
                                        host_dir=self.root_dir)

    def copy_auth_keys(self):
        ssh_dir = os.path.join(self.root_dir, 'root/.ssh')
        if not os.path.exists(ssh_dir):
            os.mkdir(ssh_dir, 0700)

        key_file = open(self.auth_keys)
        destination = open(os.path.join(ssh_dir, 'authorized_keys'), 'wb')
        destination.write(key_file.read())
        destination.close()
        key_file.close()

    def start_ssh_server(self):
        self.copy_auth_keys()
        ssh_config = self.create_ssh_config()
        host_config_path = os.path.join(self.root_dir, 'etc/ssh/sshd_config')

        sshf = open(host_config_path, 'wb')
        sshf.write(ssh_config)
        sshf.close()

        start_ssh = '/usr/sbin/sshd -f %s' % host_config_path
        self.cmd(shlex.split(start_ssh))

    def stop_ssh_server(self):
        kill_ssh = "/bin/kill $(cat %s)" % self.ssh_pid_file
        self.cmd(shlex.split(kill_ssh))

    def clean_all(self):
        pass


def load_config(config_file):
    cfg = open(config_file)
    config = yaml.load(cfg)
    cfg.close()

    return config


def setup_controllers(net, config):
    for controller in config['controllers']:
        ctrl = RemoteController(controller['name'],
                                ip=controller['ip'],
                                port=controller['port'])
        info( '*** Adding controller\n' )
        net.addController( ctrl )


def setup_hosts(net, switches, config):
    info('*** Adding hosts\n')
    hosts = {}

    ssh_template = None
    auth_keys = None

    if 'ssh' in config['general']:
        template = config['general']['ssh']['template']
        tmpl_dir = config['general']['ssh']['tmpl_dir']

        env = Environment(loader=FileSystemLoader(tmpl_dir))
        ssh_template = env.get_template(template)
        auth_keys = config['general']['ssh']['authorized_keys']

    for host in config['hosts']:
        if host['is_manageable']:
            new_host = net.addHost(host['name'], ip=None,
                                   cls=ManageableHost,
                                   root_fs=config['general']['rootfs'],
                                   ssh_template=ssh_template,
                                   auth_keys=auth_keys)
            new_host.mount_root_fs()
        else:
            new_host = net.addHost(host['name'])

        host_switches = []

        for link in host['links']:
            switch = switches[link['sw']]
            lnk = net.addLink(new_host, switch)

            if link.has_key('ip'):
               ip, netmask = link['ip'].split('/')
               new_host.setIP(ip, prefixLen=netmask, intf=lnk.intf1)

        if host.has_key('gw'):
            new_host.sendCmd('ip route add default via %s' % host['gw'])
            new_host.waiting = False

        if not hosts.has_key(host['name']):
            hosts[host['name']] = {'node': new_host, 'rootfs': new_host.name}

    return hosts


def setup_switches(net, config):
    switches = {}
    info( '*** Adding switches\n' )
    # first loop : create switches
    for switch in config['switches']:
        switches[switch['name']] = net.addSwitch( switch['name'],
                                                  dpid=switch['dpid'] )
    # second loop: add links between switches
    for switch in config['switches']:
        if switch.has_key('links'):
            for peer in switch['links']:
                net.addLink(switches[switch['name']],
                            switches[peer])

    return switches


def setup_nat(net, config):
    node = None
    if 'general' in config:
        if 'nat' in config['general']:
            info('*** Setup nat gateway node\n')
            node = connectToInternet(net,
                                     switch='o1',
                                     node_name=config['general']['nat']['node']['name'],
                                     ip_address=config['general']['nat']['node']['ip'])

            info('*** Starting nat\n')
            startNAT(node,
                     inetIntf=config['general']['nat']['ext_iface'],
                     intIP=config['general']['nat']['node']['ip'])

    return node


def tear_down_nat(node):
    info('*** Stopping nat\n')
    stopNAT(node)


def start(net):
    for name, node in net.items():
        if isinstance(node, ManageableHost):
            #node.mount_root_fs()
            node.start_ssh_server()

    info('*** Starting network\n')
    net.start()

    info('*** Starting CLI\n')
    CLI(net)


def stop(net):
    for name, node in net.items():
        if isinstance(node, ManageableHost):
            node.stop_processes()
            node.umount_root_fs()

    info('*** Stopping network\n')
    net.stop()


def setup_topo(config):

    net = Mininet(controller=RemoteController)

    setup_controllers(net, config)
    switches = setup_switches(net, config)
    hosts = setup_hosts(net, switches, config)

    nat_node = setup_nat(net, config)

    start(net)

    if nat_node:
        tear_down_nat(nat_node)

    stop(net)


if __name__ == '__main__':
    setLogLevel( 'info')

    parser = argparse.ArgumentParser(description='Minilab arguments.')
    parser.add_argument('config', metavar='config', type=str,
                        help='lab configuration file')

    args = parser.parse_args()

    topo_config = load_config(args.config)
    setup_topo(topo_config)
