#!/usr/bin/python

"""
Minilab is a network lab simulator based on
mininet. Its goal is to provide an easy way
to setup and test any kind of complex network.

"""

import subprocess
import shlex
import argparse
import yaml
import os
import time
import glob

from mininet.net import Mininet
from mininet.node import Host, OVSSwitch, RemoteController
from mininet.log import setLogLevel, info
from mininet.cli import CLI

from jinja2 import FileSystemLoader, Environment

from nat import *


class ManageableHost(Host):
    def __init__(self, name, ip=None, inNamespace=True,
                 labdir='/var/minilab', root_fs=None,
                 ssh_template=None, auth_keys=None, **kwargs):

        self.name = name
        self.root_fs = root_fs
        self.lab_dir = labdir
        self.ssh_template = ssh_template
        self.auth_keys = auth_keys
        self.root_dir = None
        self.ssh_pid_file = None
        self.mounted_dirs = []

        Host.__init__(self, name, inNamespace, **kwargs)

    def list_processes(self):
        process_list = []
        my_ns_symlink = '/proc/%s/ns/net' % self.pid
        for symlink in glob.glob('/proc/[1-9]*/ns/net'):
            pid = None
            try:
                if os.path.samefile(my_ns_symlink, symlink):
                    pid = symlink.split('/')[2]
            except:
                pass
            else:
                if pid and int(pid) != self.pid:
                    process_list.append(pid)

        return process_list

    def stop_all_processes(self):
        info('**** Stopping all remaining processes on %s\n' % self.name)
        running_processes = self.list_processes()

        for process in running_processes:
            cmd = "kill -9 %s" % process
            info('**** killing process id %s\n' % process)
            subprocess.call(shlex.split(cmd))
            time.sleep(1)

    def stop_processes(self):
        self.stop_ssh_server()
        time.sleep(1)
        self.stop_all_processes()

    def mount_root_fs(self):
        info('**** Mounting filesystem for %s\n' % self.name)
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
        info('**** Unmounting filesystem for %s\n' % self.name)
        for mount_point in self.mounted_dirs:
            subprocess.call(shlex.split("umount %s" % mount_point))

        # fixme: currently need to umount /sys
        # subprocess.call(shlex.split("umount %s" % '/sys'))

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
        if self.auth_keys:
            self.copy_auth_keys()

        ssh_config = self.create_ssh_config()
        host_config_path = os.path.join(self.root_dir, 'etc/ssh/sshd_config')

        sshf = open(host_config_path, 'wb')
        sshf.write(ssh_config)
        sshf.close()

        info('**** Starting ssh server on %s\n' % self.name)
        start_ssh = '/usr/sbin/sshd -f %s' % host_config_path
        self.cmd(shlex.split(start_ssh))

    def stop_ssh_server(self):
        info('**** Stopping ssh server on %s\n' % self.name)
        kill_ssh = "/bin/kill $(cat %s)" % self.ssh_pid_file
        self.cmd(shlex.split(kill_ssh))

    def clean_all(self):
        pass


def load_config(config_file):
    cfg = open(config_file)
    config = yaml.load(cfg)
    cfg.close()

    return config


def setup_controllers(net, topology):
    for controller in topology['controllers']:
        ctrl = RemoteController(controller['name'],
                                ip=controller['ip'],
                                port=controller['port'])
        info('*** Adding controller\n')
        net.addController(ctrl)


def setup_hosts(net, switches, config, topology):
    info('*** Adding hosts\n')
    hosts = {}

    ssh_template = None
    auth_keys = None

    if 'ssh' in config:
        template = config['ssh']['template']
        tmpl_dir = config['ssh']['tmpl_dir']

        env = Environment(loader=FileSystemLoader(tmpl_dir))
        ssh_template = env.get_template(template)
        if 'authorized_keys' in config['ssh']:
            auth_keys = config['ssh']['authorized_keys']

    for host in topology['hosts']:
        if host['is_manageable']:
            new_host = net.addHost(host['name'], ip=None,
                                   cls=ManageableHost,
                                   root_fs=config['rootfs'],
                                   ssh_template=ssh_template,
                                   auth_keys=auth_keys)
            new_host.mount_root_fs()
        else:
            new_host = net.addHost(host['name'])

        for link in host['links']:
            switch = switches[link['sw']]
            lnk = net.addLink(new_host, switch)

            if 'ip' in link:
                ip, netmask = link['ip'].split('/')
                new_host.setIP(ip, prefixLen=netmask, intf=lnk.intf1)

        if 'gw' in host:
            new_host.sendCmd('ip route add default via %s' % host['gw'])
            new_host.waiting = False

        if not host['name'] in hosts:
            hosts[host['name']] = {'node': new_host, 'rootfs': new_host.name}

    return hosts


def setup_switches(net, topology):
    switches = {}
    info('*** Adding switches\n')
    # first loop : create switches
    for switch in topology['switches']:
        if 'protocols' in switch:
            protocols = ','.join(switch['protocols'])
        else:
            protocols = 'OpenFlow13'

        switches[switch['name']] = net.addSwitch(switch['name'],
                                                 dpid=switch['dpid'],
                                                 cls=OVSSwitch,
                                                 protocols=protocols)
    # second loop: add links between switches
    for switch in topology['switches']:
        if 'links' in switch:
            for peer in switch['links']:
                net.addLink(switches[switch['name']],
                            switches[peer])

    return switches


def setup_nat(net, topology):
    node = None
    if 'nat' in topology:
        info('*** Setup nat gateway node\n')
        node = connectToInternet(net,
                                 switch=topology['nat']['switch']['name'],
                                 node_name=topology['nat']['node']['name'],
                                 ip_address=topology['nat']['node']['ip'])

        info('** Starting nat\n')
        startNAT(node,
                 inetIntf=topology['nat']['ext_iface'],
                 intIP=topology['nat']['node']['ip'])

    return node


def fix_switch_protocols(topology):
    """ force protocols versions as mininet < 2.2.0 is not doing its job"""

    for switch in topology['switches']:
        if 'protocols' in switch:
            protocols = ','.join(switch['protocols'])
        else:
            protocols = 'OpenFlow13'

        cmd = "ovs-vsctl set Bridge %s protocols=%s" % (switch['name'],
                                                        protocols)
        subprocess.call(shlex.split(cmd))


def tear_down_nat(node):
    info('** Stopping nat\n')
    stopNAT(node)


def start(net):
    for name, node in net.items():
        if isinstance(node, ManageableHost):
            node.start_ssh_server()

    info('** Starting network\n')
    net.start()

    fix_switch_protocols(topology)

    CLI(net)


def stop(net):
    for name, node in net.items():
        if isinstance(node, ManageableHost):
            node.stop_processes()
            node.umount_root_fs()

    info('** Stopping network\n')
    net.stop()


def setup_topo(config, topology):

    net = Mininet(controller=RemoteController)

    setup_controllers(net, topology)
    switches = setup_switches(net, topology)
    hosts = setup_hosts(net, switches, config, topology)

    nat_node = setup_nat(net, topology)

    start(net)

    if nat_node:
        tear_down_nat(nat_node)

    stop(net)


if __name__ == '__main__':
    setLogLevel('info')

    parser = argparse.ArgumentParser(description='Minilab arguments.')
    parser.add_argument('--config', dest='config', type=str,
                        default='config.yaml',
                        help='minilab config file (default: config.yaml)')
    parser.add_argument('topology', metavar='topology', type=str,
                        help='topology configuration file')

    args = parser.parse_args()

    minilab_config = load_config(args.config)
    topo_config = load_config(args.topology)
    setup_topo(minilab_config, topo_config)
